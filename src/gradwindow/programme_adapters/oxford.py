from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-oxford"
CATALOG_URL = "https://www.ox.ac.uk/admissions/graduate/courses/courses-a-z-listing"
APPLICATION_URL = (
    "https://www.ox.ac.uk/admissions/graduate/application-guide/"
    "starting-your-application/your-application-account"
)
DEFAULT_INTAKE = "2027-28"
COURSE_PATH_RE = re.compile(
    r"^/admissions/graduate/courses/(?P<slug>[a-z0-9][a-z0-9-]+?)/?$",
    flags=re.IGNORECASE,
)
MASTER_DEGREE_RE = re.compile(
    r"\b(?P<degree>MPhil|MSc|MSt|MBA|EMBA|MPP|MFA|MTh|BCL|MJur|MCL|"
    r"MFin|LLM|MPH|MEd|MMus|MRes|MLitt)\b",
    flags=re.IGNORECASE,
)
RESEARCH_MASTER_RE = re.compile(r"\bMSc\s+by\s+Research\b", flags=re.IGNORECASE)
OXFORD_RESEARCH_MPHIL_TITLES = {"law", "socio-legal research"}
EXCLUDED_COURSE_SLUGS = {
    "changes-to-courses",
    "courses-a-z-listing",
    "departments",
    "find-your-course",
    "open-courses",
    "research-courses",
    "taught-courses",
    "ucas-listings",
}
DATE_RE = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<year>20\d{2})\b",
    flags=re.IGNORECASE,
)
US_DATE_RE = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<day>\d{1,2}),\s+(?P<year>20\d{2})\b",
    flags=re.IGNORECASE,
)
EXPECTED_START_RE = re.compile(
    r"Expected\s+start\s+date\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?P<year>20\d{2})",
    flags=re.IGNORECASE,
)
UPCOMING_CYCLE_RE = re.compile(
    r"applications\s+open\s*\(for\s+entry\s+in\s+(?P<intake>20\d{2}-\d{2})\)",
    flags=re.IGNORECASE,
)


class OxfordAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = DEFAULT_INTAKE
    application_opens_at_basis = "missing"

    def __init__(
        self,
        minimum_expected_programmes: int = 125,
        detail_workers: int = 6,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_html = fetcher(self.catalog_url)
        last_page = _last_page_number(BeautifulSoup(first_html, "html.parser"))
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
        programmes = self._unique_programmes(programmes)
        self._validate_catalog_size(programmes)

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return self._parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        "Programme found in Oxford's official A-Z catalogue, but "
                        "the course page could not be fetched during discovery: "
                        f"{type(exc).__name__}: {str(exc)[:180]}"
                    ),
                    parse_status="no-deadline",
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = list(executor.map(parse_one, programmes))
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        programmes = self._unique_programmes(self._parse_programmes(html))
        self._validate_catalog_size(programmes)
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _parse_programmes(self, html: str) -> list[DiscoveredProgramme]:
        soup = BeautifulSoup(html, "html.parser")
        programmes = []
        for link in soup.find_all("a", href=True):
            programme = self._parse_course_link(link)
            if programme is not None:
                programmes.append(programme)
        return programmes

    def _parse_course_link(self, link) -> DiscoveredProgramme | None:
        source_url = _course_url(link.get("href", ""))
        if source_url is None:
            return None
        title = _normalise_text(link.get_text(" ", strip=True))
        if not title:
            return None
        context = _degree_context(link, title)
        if context is None:
            return None
        degree_match = MASTER_DEGREE_RE.search(context)
        if degree_match is None or RESEARCH_MASTER_RE.search(context):
            return None
        degree_type = _canonical_degree(degree_match.group("degree"))
        if degree_type == "MPhil" and title.casefold() in OXFORD_RESEARCH_MPHIL_TITLES:
            return None
        faculty = _course_faculty(link)
        return DiscoveredProgramme(
            id=_programme_id(title, degree_type),
            name=_programme_name(title, degree_type),
            degree_type=degree_type,
            faculty=faculty,
            department="",
            source_url=source_url,
            application_url=self.application_url,
            windows=[],
            deadline_text=(
                "Programme found in Oxford's official A-Z graduate course "
                "catalogue; no exact application deadline was parsed from the "
                "catalogue row."
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
        h1 = soup.find("h1")
        name = _normalise_text(h1.get_text(" ", strip=True)) if h1 is not None else ""
        intake = _intake_from_detail(text)
        deadlines, excerpt = _application_deadlines(text)
        if not deadlines:
            return replace(
                programme,
                name=name or programme.name,
                deadline_text=_status_excerpt(text) or programme.deadline_text,
            )
        windows = [
            DiscoveredWindow(
                round=(
                    "Main application deadline"
                    if len(deadlines) == 1
                    else f"Application deadline {index}"
                ),
                opens_at=None,
                closes_at=deadline,
                intake=intake,
            )
            for index, deadline in enumerate(deadlines, start=1)
        ]
        return replace(
            programme,
            name=name or programme.name,
            windows=windows,
            deadline_text=excerpt,
            parse_status="incomplete",
        )

    @staticmethod
    def _unique_programmes(
        programmes: list[DiscoveredProgramme],
    ) -> list[DiscoveredProgramme]:
        return sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )

    def _validate_catalog_size(
        self,
        programmes: list[DiscoveredProgramme],
    ) -> None:
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Oxford A-Z catalogue only contained "
                f"{len(programmes)} taught master's programmes; expected at least "
                f"{self.minimum_expected_programmes}. The response may be blocked "
                "or pagination may be incomplete."
            )


def _course_url(href: str) -> str | None:
    absolute = urljoin(CATALOG_URL, href)
    parts = urlsplit(absolute)
    if parts.hostname not in {"ox.ac.uk", "www.ox.ac.uk"}:
        return None
    match = COURSE_PATH_RE.match(parts.path.rstrip("/"))
    if match is None or match.group("slug").casefold() in EXCLUDED_COURSE_SLUGS:
        return None
    return f"https://www.ox.ac.uk{parts.path.rstrip('/')}"


def _degree_context(link, title: str) -> str | None:
    node = link
    for _ in range(7):
        node = node.parent
        if node is None:
            return None
        text = _normalise_text(node.get_text(" ", strip=True))
        if len(text) > 700:
            continue
        remainder = text.replace(title, "", 1).strip()
        if MASTER_DEGREE_RE.search(remainder):
            return remainder
    return None


def _course_faculty(link) -> str:
    node = link
    for _ in range(7):
        node = node.parent
        if node is None:
            return ""
        for selector in (
            ".course-department",
            ".department",
            '[class*="department"]',
            '[class*="subject"]',
        ):
            field = node.select_one(selector)
            if field is not None:
                value = _normalise_text(field.get_text(" ", strip=True))
                if value:
                    return value
    return ""


def _application_deadlines(text: str) -> tuple[list[str], str]:
    lower = text.casefold()
    positions = [
        match.start() for match in re.finditer(r"application\s+deadlines?", lower)
    ]
    if not positions:
        return [], ""
    excerpts = []
    dates = []
    for position in positions:
        excerpt = text[max(0, position - 100) : position + 900]
        excerpts.append(excerpt)
        for match in DATE_RE.finditer(excerpt):
            dates.append(_date_from_match(match))
        for match in US_DATE_RE.finditer(excerpt):
            dates.append(_date_from_match(match))
    unique_dates = sorted(set(dates))
    return unique_dates, _normalise_text(" ".join(excerpts))[:1800]


def _date_from_match(match: re.Match[str]) -> str:
    value = f"{match.group('day')} {match.group('month')} {match.group('year')}"
    return datetime.strptime(value, "%d %B %Y").date().isoformat()


def _intake_from_detail(text: str) -> str:
    match = EXPECTED_START_RE.search(text)
    if match:
        return f"{match.group('month').title()} {match.group('year')}"
    upcoming = UPCOMING_CYCLE_RE.search(text)
    if upcoming:
        return upcoming.group("intake")
    return DEFAULT_INTAKE


def _status_excerpt(text: str) -> str:
    status_markers = (
        "Closed to applications",
        "Applications are still open",
        "Register to receive an email",
    )
    positions = [text.find(marker) for marker in status_markers if marker in text]
    if not positions:
        return ""
    start = min(position for position in positions if position >= 0)
    return text[start : start + 600]


def _last_page_number(soup: BeautifulSoup) -> int:
    pages = set()
    for link in soup.select('a[href*="page="]'):
        match = re.search(r"[?&]page=(\d+)", link.get("href", ""))
        if match:
            pages.add(int(match.group(1)))
    return max(pages) if pages else 0


def _canonical_degree(value: str) -> str:
    canonical = {
        "emba": "EMBA",
        "mba": "MBA",
        "bcl": "BCL",
        "mjur": "MJur",
    }
    return canonical.get(value.casefold(), value[0].upper() + value[1:])


def _programme_name(title: str, degree_type: str) -> str:
    if re.search(rf"\b{re.escape(degree_type)}\b", title, flags=re.IGNORECASE):
        return title
    return f"{degree_type} in {title}"


def _programme_id(title: str, degree_type: str) -> str:
    return f"oxford-{_slug(title)}-{_slug(degree_type)}"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
