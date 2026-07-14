from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

CATALOG_URL = "https://www.gs.cuhk.edu.hk/admissions/application-deadline"
APPLICATION_URL = "https://www.gradsch.cuhk.edu.hk/OnlineApp/login_email.aspx"
UNIVERSITY_ID = "the-chinese-university-of-hong-kong"

MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?"
)
DATE_RE = re.compile(
    rf"\b(?P<date>\d{{1,2}}\s+(?:{MONTHS})\s+20\d{{2}})\b",
    flags=re.IGNORECASE,
)
OPEN_DATE_RE = re.compile(
    rf"Application Commencement Date[^:]*:\s*(?P<date>\d{{1,2}}\s+"
    rf"(?:{MONTHS})\s+20\d{{2}})",
    flags=re.IGNORECASE,
)


class CUHKAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "September 2026"

    def __init__(self, minimum_expected_programmes: int = 100) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        page_text = " ".join(soup.get_text(" ", strip=True).split())
        open_match = OPEN_DATE_RE.search(page_text)
        if open_match is None:
            raise ValueError("CUHK application commencement date was not found")
        opens_at = _parse_date(open_match.group("date"))

        programmes: list[DiscoveredProgramme] = []
        for group in soup.select(".view-grouping"):
            faculty_node = group.select_one(":scope > .view-grouping-header")
            if faculty_node is None:
                continue
            faculty = _normalise_text(faculty_node.get_text(" ", strip=True))
            for division in group.select(".collapse-item"):
                department_node = division.select_one(
                    ":scope > .collapse-item-header span"
                )
                if department_node is None:
                    continue
                department = _normalise_text(department_node.get_text(" ", strip=True))
                content = division.select_one(":scope > .collapse-item-content")
                if content is None:
                    continue
                programmes.extend(self._parse_department(content, faculty, department))

        unique = {item.id: item for item in programmes}
        programmes = sorted(unique.values(), key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "CUHK catalog only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=programmes,
        )

    def _parse_department(
        self,
        content,
        faculty: str,
        department: str,
    ) -> list[DiscoveredProgramme]:
        programmes: list[DiscoveredProgramme] = []
        for column in content.select(":scope > .col-12"):
            heading = column.find(["h2", "h3"], recursive=False)
            if heading is None or "Taught Programmes" not in heading.get_text(
                " ", strip=True
            ):
                continue
            for box in column.select(":scope > .MAinAnthropology"):
                title_node = box.select_one(":scope > .title-bg")
                deadline_node = box.select_one(":scope > .content-bg")
                if title_node is None or deadline_node is None:
                    continue
                title = _normalise_text(title_node.get_text(" ", strip=True))
                degree_type = _degree_type(title)
                if degree_type is None:
                    continue
                windows = _parse_windows(deadline_node)
                programmes.append(
                    DiscoveredProgramme(
                        id=_programme_id(title),
                        name=title,
                        degree_type=degree_type,
                        faculty=faculty,
                        department=department,
                        source_url=self.catalog_url,
                        application_url=self.application_url,
                        windows=windows,
                        deadline_text=_normalise_text(
                            deadline_node.get_text(" ", strip=True)
                        ),
                        parse_status="parsed" if windows else "no-deadline",
                    )
                )
        return programmes


def _parse_windows(node) -> list[DiscoveredWindow]:
    windows: list[DiscoveredWindow] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for raw_segment in node.stripped_strings:
        segment = _normalise_text(str(raw_segment))
        lowered = segment.lower()
        if (
            "applications submitted" in lowered
            or "applications may be submitted" in lowered
        ):
            continue
        match = DATE_RE.search(segment)
        if match is None:
            continue
        label = segment[: match.start()].strip(" :-–")
        suffix = segment[match.end() :].strip()
        if not label and re.match(r"^\(\s*Early Round\s*\)", suffix, re.I):
            label = "Early round"
        round_label, categories = _normalise_round(label)
        closes_at = _parse_date(match.group("date"))
        key = (round_label, closes_at, tuple(categories))
        if key in seen:
            continue
        seen.add(key)
        windows.append(
            DiscoveredWindow(
                round=round_label,
                closes_at=closes_at,
                applicant_categories=categories,
            )
        )
    return windows


def _normalise_round(label: str) -> tuple[str, list[str]]:
    if not label:
        return "Main application period", ["all"]
    lowered = label.lower().replace("around", "round")
    if lowered == "for non-local applicants":
        return "Non-local applicants", ["international-students"]
    if lowered == "for local applicants":
        return "Local applicants", ["domestic-students"]
    if lowered == "round":
        return "Main round", ["all"]
    clean = re.sub(r"\s+", " ", lowered).strip()
    if re.match(r"^\d+(?:st|nd|rd|th)\s", clean):
        return clean, ["all"]
    return clean.capitalize(), ["all"]


def _degree_type(title: str) -> str | None:
    excluded = (
        "Doctor of ",
        "Juris Doctor",
        "PgD ",
        "Postgraduate Certificate",
    )
    if title.startswith(excluded):
        return None
    for prefix, degree in (
        ("MSc in ", "MSc"),
        ("MSSc in ", "MSSc"),
        ("MA in ", "MA"),
        ("MBA in ", "MBA"),
        ("Executive MBA", "MBA"),
        ("MBA", "MBA"),
        ("Executive Master of ", "Master"),
        ("Master of ", "Master"),
        ("Dual Degree - MSc in ", "MSc"),
    ):
        if title.startswith(prefix):
            return degree
    return None


def _programme_id(title: str) -> str:
    rules = (
        (r"^MSc in (.+)$", "msc"),
        (r"^MSSc in (.+)$", "mssc"),
        (r"^MA in (.+)$", "ma"),
        (r"^MBA in (.+)$", "mba"),
        (r"^Executive Master of (.+)$", "executive-master"),
        (r"^Master of (.+)$", "master"),
    )
    for pattern, suffix in rules:
        match = re.match(pattern, title, flags=re.IGNORECASE)
        if match:
            return f"cuhk-{_slug(match.group(1))}-{suffix}"
    return f"cuhk-{_slug(title)}"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _parse_date(value: str) -> str:
    normalised = re.sub(r"\s+", " ", value.strip())
    for pattern in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(normalised, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported CUHK date: {value}")


def _normalise_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())
