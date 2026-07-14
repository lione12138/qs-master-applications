from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "eth-zurich-swiss-federal-institute-of-technology"
PROFILE_REQUIREMENTS_URL = (
    "https://ethz.ch/en/studies/master/application/profile-requirements.html"
)
DATES_URL = "https://ethz.ch/en/studies/master/application/dates.html"
APPLICATION_URL = "https://ethz.ch/en/studies/master/application.html"
DEFAULT_INTAKE = "Autumn 2026"

DEGREE_AT_END_RE = re.compile(r"\b(?P<degree>MSc|MA)\s*$")
PDF_SUFFIX_RE = re.compile(r"\s*\(PDF,.*?\)\s*$", flags=re.IGNORECASE)
INTAKE_RE = re.compile(
    r"Application Dates\s+(?P<term>Autumn) Semester\s+(?P<year>20\d{2})"
)
DATE_RANGE_RE = re.compile(
    r"(?P<start_day>\d{1,2})\s+"
    r"(?:(?P<start_month>[A-Z][a-z]+)\s+)?"
    r"[-–]\s+"
    r"(?P<end_day>\d{1,2})\s+"
    r"(?P<end_month>[A-Z][a-z]+)\s+"
    r"(?P<year>20\d{2})"
)


class ETHAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = PROFILE_REQUIREMENTS_URL
    application_url = APPLICATION_URL
    intake = DEFAULT_INTAKE

    def __init__(self, minimum_expected_programmes: int = 40) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        windows, intake = _parse_windows(fetcher(DATES_URL))
        self.intake = intake
        return self.parse_catalog(fetcher(self.catalog_url), windows=windows)

    def parse_catalog(
        self,
        html: str,
        *,
        windows: list[DiscoveredWindow] | None = None,
    ) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        programme_windows = windows or _default_windows()
        programmes = _dedupe_programmes(
            programme
            for wrapper in soup.select(".linklist__wrapper")
            for programme in _parse_wrapper(wrapper, programme_windows)
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "ETH Zurich profile requirements page only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _parse_wrapper(
    wrapper, windows: list[DiscoveredWindow]
) -> list[DiscoveredProgramme]:
    heading = wrapper.find("h2")
    faculty = _normalise_text(heading.get_text(" ", strip=True)) if heading else ""
    programmes = []
    for link in wrapper.select('a[href*="/master-profile/englisch/"][href*=".pdf"]'):
        source_url = urljoin(PROFILE_REQUIREMENTS_URL, link["href"])
        for title, degree_type in _programme_titles(link):
            programmes.append(
                DiscoveredProgramme(
                    id=_programme_id(title, degree_type),
                    name=f"{degree_type} {title}",
                    degree_type=degree_type,
                    faculty=faculty,
                    department=title,
                    source_url=source_url,
                    application_url=APPLICATION_URL,
                    windows=list(windows),
                    deadline_text=_deadline_text(title, degree_type, windows),
                    parse_status="parsed",
                )
            )
    return programmes


def _programme_titles(link) -> list[tuple[str, str]]:
    text = _normalise_text(link.get_text(" ", strip=True))
    text = re.sub(r"^Download\s+", "", text)
    text = PDF_SUFFIX_RE.sub("", text)
    titles = []
    for part in [value.strip() for value in text.split(" / ") if value.strip()]:
        match = DEGREE_AT_END_RE.search(part)
        if match is None:
            continue
        degree_type = match.group("degree")
        title = _normalise_text(part[: match.start()])
        if title:
            titles.append((title, degree_type))
    return titles


def _parse_windows(html: str) -> tuple[list[DiscoveredWindow], str]:
    soup = BeautifulSoup(html, "html.parser")
    title = _normalise_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    intake = _parse_intake(title) or DEFAULT_INTAKE
    windows = []
    for heading in soup.find_all("h2"):
        text = _normalise_text(heading.get_text(" ", strip=True))
        if "Bachelor" not in text:
            continue
        range_match = DATE_RANGE_RE.search(text)
        if range_match is None:
            continue
        opens_at, closes_at = _dates_from_range(range_match)
        if "International" in text:
            windows.append(
                DiscoveredWindow(
                    round="International Bachelor's window",
                    applicant_categories=[
                        "international-bachelors",
                        "esop",
                        "direct-doctorate",
                    ],
                    opens_at=opens_at,
                    closes_at=closes_at,
                    intake=intake,
                )
            )
        elif "Swiss" in text:
            windows.append(
                DiscoveredWindow(
                    round="Swiss Bachelor's window",
                    applicant_categories=["swiss-bachelors"],
                    opens_at=opens_at,
                    closes_at=closes_at,
                    intake=intake,
                )
            )
    if len(windows) < 2:
        raise ValueError(
            "ETH Zurich dates page did not contain both application windows"
        )
    return windows, intake


def _dates_from_range(match: re.Match[str]) -> tuple[str, str]:
    end_month = match.group("end_month")
    start_month = match.group("start_month") or end_month
    year = int(match.group("year"))
    opens_at = datetime.strptime(
        f"{match.group('start_day')} {start_month} {year}",
        "%d %B %Y",
    ).date()
    closes_at = datetime.strptime(
        f"{match.group('end_day')} {end_month} {year}",
        "%d %B %Y",
    ).date()
    return opens_at.isoformat(), closes_at.isoformat()


def _parse_intake(title: str) -> str | None:
    match = INTAKE_RE.search(title)
    if match is None:
        return None
    return f"{match.group('term')} {match.group('year')}"


def _default_windows() -> list[DiscoveredWindow]:
    return [
        DiscoveredWindow(
            round="International Bachelor's window",
            applicant_categories=[
                "international-bachelors",
                "esop",
                "direct-doctorate",
            ],
            opens_at="2025-11-01",
            closes_at="2025-11-30",
            intake=DEFAULT_INTAKE,
        ),
        DiscoveredWindow(
            round="Swiss Bachelor's window",
            applicant_categories=["swiss-bachelors"],
            opens_at="2026-04-01",
            closes_at="2026-04-30",
            intake=DEFAULT_INTAKE,
        ),
    ]


def _dedupe_programmes(
    programmes: Iterable[DiscoveredProgramme],
) -> list[DiscoveredProgramme]:
    by_id: dict[str, DiscoveredProgramme] = {}
    for programme in programmes:
        previous = by_id.get(programme.id)
        if previous is None:
            by_id[programme.id] = programme
            continue
        faculties = _join_unique(previous.faculty, programme.faculty)
        by_id[programme.id] = DiscoveredProgramme(
            id=previous.id,
            name=previous.name,
            degree_type=previous.degree_type,
            faculty=faculties,
            department=previous.department,
            source_url=previous.source_url,
            application_url=previous.application_url,
            windows=previous.windows,
            deadline_text=previous.deadline_text,
            parse_status=previous.parse_status,
        )
    return sorted(by_id.values(), key=lambda item: item.id)


def _join_unique(*values: str) -> str:
    seen = []
    for value in values:
        for part in str(value).split(" | "):
            cleaned = _normalise_text(part)
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
    return " | ".join(seen)


def _deadline_text(
    title: str,
    degree_type: str,
    windows: list[DiscoveredWindow],
) -> str:
    window_text = "; ".join(
        f"{window.round}: {window.opens_at} to {window.closes_at}" for window in windows
    )
    return (
        f"ETH Zurich lists {title} {degree_type} in its official profiles of "
        f"requirements. The official application dates page lists {windows[0].intake} "
        f"master's application windows: {window_text}."
    )


def _programme_id(title: str, degree_type: str) -> str:
    if title == "Robotics, Systems and Control" and degree_type == "MSc":
        return "eth-robotics-systems-control-msc"
    return f"eth-{_slug(title)}-{_slug(degree_type)}"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
