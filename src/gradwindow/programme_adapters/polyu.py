from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

CATALOG_URL = "https://www.polyu.edu.hk/study/pg/taught-postgraduate"
APPLICATION_URL = "https://www38.polyu.edu.hk/eAdmission/index.do"
UNIVERSITY_ID = "the-hong-kong-polytechnic-university"

DEADLINE_RE = re.compile(
    r"(?P<category>Local|Non-Local)\s+Application\s+Deadline:\s+"
    r"(?P<date>\d{1,2}\s+[A-Za-z]{3}\s+20\d{2})"
    r"(?:\s+\((?P<round>[^)]+)\))?",
    flags=re.IGNORECASE,
)


class PolyUAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL

    def __init__(
        self,
        minimum_expected_programmes: int = 80,
        intake: str = "September 2027",
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.intake = intake

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        opens_at = _application_start_date(soup)
        programmes = [
            programme
            for link in soup.select('a.programme[href*="/study/pg/tpg/"]')
            if (programme := self._parse_programme(link)) is not None
        ]
        unique = {programme.id: programme for programme in programmes}
        programmes = sorted(unique.values(), key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "PolyU catalog only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=programmes,
        )

    def _parse_programme(self, link) -> DiscoveredProgramme | None:
        entry_text = _normalise_text(
            (
                link.select_one(".programmes-code-and-entry-description") or link
            ).get_text(" ", strip=True)
        )
        if "Sept 2027 Entry" not in entry_text:
            return None
        title_node = link.select_one(".title")
        if title_node is None:
            return None
        title_parts = [
            _normalise_text(part)
            for part in title_node.get_text(" ", strip=True).split(" - ")
            if _normalise_text(part)
        ]
        if len(title_parts) < 2:
            return None
        subject = title_parts[0]
        degree_type = title_parts[1]
        if not _is_master_degree(degree_type, title_parts):
            return None

        href = urljoin(self.catalog_url, link["href"])
        windows = _parse_windows(link)
        return DiscoveredProgramme(
            id=_programme_id(subject, degree_type),
            name=_programme_name(subject, degree_type),
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=href,
            application_url=self.application_url,
            windows=windows,
            deadline_text=_normalise_text(
                (link.select_one(".deadline-section") or link).get_text(" ", strip=True)
            ),
            parse_status="parsed" if windows else "no-deadline",
        )


def _application_start_date(soup: BeautifulSoup) -> str | None:
    for image in soup.find_all("img", alt=True):
        if "application starts" not in image["alt"].lower():
            continue
        event = image.find_parent(class_="event")
        date_node = event.select_one("[data-start-date]") if event else None
        if date_node and date_node.get("data-start-date"):
            return date_node["data-start-date"]
    return None


def _parse_windows(link) -> list[DiscoveredWindow]:
    deadline_section = link.select_one(".deadline-section")
    if deadline_section is None:
        return []
    windows: list[DiscoveredWindow] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for text in deadline_section.stripped_strings:
        match = DEADLINE_RE.search(_normalise_text(text))
        if match is None:
            continue
        category = match.group("category").lower()
        categories = (
            ["domestic-students"] if category == "local" else ["international-students"]
        )
        round_label = _normalise_round(match.group("round") or "Main round")
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


def _is_master_degree(degree_type: str, title_parts: list[str]) -> bool:
    joined = " ".join(title_parts).lower()
    if "doctor" in joined or "bachelor" in joined:
        return False
    return bool(
        re.search(
            r"\b(MSc|MA|MBA|MDes|MPhil|Master|LLM|MEd|MSocSc|MPA|MPH)\b",
            degree_type,
            flags=re.IGNORECASE,
        )
    )


def _programme_name(subject: str, degree_type: str) -> str:
    if degree_type.upper() == "MSC":
        return f"MSc in {subject}"
    if degree_type.upper() == "MA":
        return f"MA in {subject}"
    if degree_type.upper() == "MBA":
        return f"MBA in {subject}"
    if degree_type.lower() == "master":
        return f"Master of {subject}"
    return f"{degree_type} in {subject}"


def _programme_id(subject: str, degree_type: str) -> str:
    return f"polyu-{_slug(subject)}-{_slug(degree_type)}"


def _normalise_round(value: str) -> str:
    lowered = _normalise_text(value).lower()
    if lowered == "early round":
        return "Early round"
    if lowered == "main round":
        return "Main round"
    return lowered.capitalize()


def _parse_date(value: str) -> str:
    return datetime.strptime(_normalise_text(value), "%d %b %Y").date().isoformat()


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())
