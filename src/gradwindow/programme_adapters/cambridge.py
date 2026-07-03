from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

CATALOG_URL = "https://www.postgraduate.study.cam.ac.uk/courses/directory"
APPLICATION_URL = "https://apply.postgraduate.study.cam.ac.uk/applicant/login"
UNIVERSITY_ID = "university-of-cambridge"
COURSE_DATES_RE = re.compile(
    r"Applications open\s+(?P<opens>[A-Z][a-z]{2,}\.?\s+\d{1,2},\s+20\d{2})"
    r"\s+Application deadline\s+"
    r"(?P<closes>[A-Z][a-z]{2,}\.?\s+\d{1,2},\s+20\d{2})"
    r"\s+Course starts\s+"
    r"(?P<starts>[A-Z][a-z]{2,}\.?\s+\d{1,2},\s+20\d{2})",
    flags=re.IGNORECASE,
)


class CambridgeAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Michaelmas 2026"

    def __init__(
        self,
        minimum_expected_programmes: int = 100,
        detail_workers: int = 8,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_html = fetcher(self.catalog_url)
        soup = BeautifulSoup(first_html, "html.parser")
        last_page = _last_page_number(soup)
        html_pages = [first_html]
        html_pages.extend(
            fetcher(f"{self.catalog_url}?page={page}")
            for page in range(1, last_page + 1)
        )
        programmes = [
            programme
            for html in html_pages
            for programme in self._parse_programmes(html)
        ]
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = list(
                executor.map(
                    lambda programme: self._parse_detail(
                        programme,
                        fetcher(programme.source_url),
                    ),
                    programmes,
                )
            )
        return self._catalog_from_programmes(programmes)

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        return self._catalog_from_programmes(self._parse_programmes(html))

    def _parse_programmes(self, html: str) -> list[DiscoveredProgramme]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if table is None:
            raise ValueError("Cambridge course directory table was not found")
        return [
            programme
            for row in table.select("tbody tr")
            if (programme := self._parse_row(row)) is not None
        ]

    def _catalog_from_programmes(
        self,
        programmes: list[DiscoveredProgramme],
    ) -> DiscoveredCatalog:
        unique = {programme.id: programme for programme in programmes}
        programmes = sorted(unique.values(), key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Cambridge catalog only contained "
                f"{len(programmes)} taught master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _parse_row(self, row) -> DiscoveredProgramme | None:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            return None
        course_level = _normalise_text(cells[1].get_text(" ", strip=True))
        taught_or_research = _normalise_text(cells[2].get_text(" ", strip=True))
        if course_level != "Master's" or taught_or_research != "Taught":
            return None
        link = cells[0].find("a", href=True)
        if link is None:
            return None
        title = _normalise_text(link.get_text(" ", strip=True)).replace(
            " - Closed this cycle", ""
        )
        course_text = _normalise_text(cells[0].get_text(" ", strip=True)).replace(
            " - Closed this cycle", ""
        )
        degree_type = _degree_type(course_text, title)
        if degree_type is None:
            return None
        source_url = urljoin(self.catalog_url, link["href"])
        return DiscoveredProgramme(
            id=_programme_id(title, degree_type),
            name=f"{degree_type} in {title}",
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=source_url,
            application_url=self.application_url,
            windows=[],
            deadline_text=(
                "The Cambridge course directory identifies this taught master's "
                "course; exact application dates are published on the course page."
            ),
            parse_status="no-deadline",
        )

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
    ) -> DiscoveredProgramme:
        soup = BeautifulSoup(html, "html.parser")
        text = _normalise_text(soup.get_text(" ", strip=True))
        match = COURSE_DATES_RE.search(text)
        if match is None:
            return programme
        opens_at = _parse_cambridge_date(match.group("opens"))
        closes_at = _parse_cambridge_date(match.group("closes"))
        starts_at = _parse_cambridge_date(match.group("starts"))
        return replace(
            programme,
            windows=[
                DiscoveredWindow(
                    round="Main deadline",
                    opens_at=opens_at,
                    closes_at=closes_at,
                    intake=_cambridge_intake(starts_at),
                )
            ],
            deadline_text=_normalise_text(match.group(0)),
            parse_status="parsed",
        )


def _degree_type(course_text: str, title: str) -> str | None:
    suffix = course_text[len(title) :].strip()
    match = re.search(r"\b(MPhil|MSt|MRes|LLM|MBA|MEd|MFin|MMus|MCL)\b", suffix)
    return match.group(1) if match else None


def _last_page_number(soup: BeautifulSoup) -> int:
    last = 0
    for link in soup.select('a[href*="page="]'):
        match = re.search(r"[?&]page=(\d+)", link.get("href", ""))
        if match:
            last = max(last, int(match.group(1)))
    return last


def _parse_cambridge_date(value: str) -> str:
    normalised = _normalise_text(value).replace(".", "")
    for pattern in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(normalised, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported Cambridge date: {value}")


def _cambridge_intake(course_starts_at: str) -> str:
    parsed = datetime.fromisoformat(course_starts_at)
    if parsed.month in {9, 10, 11, 12}:
        return f"Michaelmas {parsed.year}"
    if parsed.month in {1, 2, 3}:
        return f"Lent {parsed.year}"
    if parsed.month in {4, 5, 6}:
        return f"Easter {parsed.year}"
    return f"{parsed.strftime('%B')} {parsed.year}"


def _programme_id(title: str, degree_type: str) -> str:
    return f"cambridge-{_slug(title)}-{_slug(degree_type)}"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())
