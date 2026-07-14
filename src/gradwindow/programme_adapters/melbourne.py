from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "the-university-of-melbourne"
HANDBOOK_ORIGIN = "https://uom-handbook.herokuapp.com"
CATALOG_FETCH_URL = f"{HANDBOOK_ORIGIN}/courses?page=1"
CATALOG_PAGE_URL = f"{HANDBOOK_ORIGIN}/courses?page={{page}}"
CANONICAL_HANDBOOK_ORIGIN = "https://handbook.unimelb.edu.au"
CATALOG_URL = f"{CANONICAL_HANDBOOK_ORIGIN}/courses"
STUDY_ORIGIN = "https://study.unimelb.edu.au"
APPLICATION_URL = f"{STUDY_ORIGIN}/how-to-apply/your-online-application"
MARKETING_PROBE_URL = (
    f"{STUDY_ORIGIN}/find/courses/graduate/"
    "master-of-information-technology/how-to-apply/"
)
TAUGHT_QUALIFICATIONS = {"Masters (Coursework)", "Masters (Extended)"}
DEADLINE_RE = re.compile(
    r"(?P<intake>Start\s+year(?:\s*\([^)]*\))?|Mid[- ]year(?:\s*\([^)]*\))?)"
    r"\s+applications?\s+(?:are\s+)?due\s+"
    r"(?P<date>\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+20\d{2})",
    re.I,
)


class MelbourneAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"

    def __init__(
        self,
        minimum_expected_programmes: int = 200,
        *,
        catalog_workers: int = 8,
        detail_workers: int = 10,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.catalog_workers = catalog_workers
        self.detail_workers = detail_workers
        self.catalogue_diagnostics = "not inspected"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_html = fetcher(CATALOG_FETCH_URL)
        page_count = _page_count(first_html)

        def fetch_page(page: int) -> str:
            if page == 1:
                return first_html
            try:
                return fetcher(CATALOG_PAGE_URL.format(page=page))
            except Exception:
                return ""

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.catalog_workers
        ) as executor:
            pages = list(executor.map(fetch_page, range(1, page_count + 1)))
        programmes = sorted(
            {
                programme.id: programme
                for html in pages
                for programme in _catalogue_programmes(html)
            }.values(),
            key=lambda item: item.id,
        )
        self.catalogue_diagnostics = (
            f"catalogPages={page_count}, "
            f"readablePages={sum(bool(page) for page in pages)}, "
            f"taughtMasters={len(programmes)}"
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "University of Melbourne Handbook only produced "
                f"{len(programmes)} taught master's programmes; expected at "
                f"least {self.minimum_expected_programmes}. "
                f"Diagnostics: {self.catalogue_diagnostics}"
            )

        probe_html = None
        try:
            probe_html = fetcher(MARKETING_PROBE_URL)
        except Exception:
            pass
        if probe_html:

            def add_deadlines(programme: DiscoveredProgramme) -> DiscoveredProgramme:
                try:
                    html = (
                        probe_html
                        if programme.application_url == MARKETING_PROBE_URL
                        else fetcher(programme.application_url)
                    )
                    return _add_course_deadlines(programme, html)
                except Exception:
                    return programme

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.detail_workers
            ) as executor:
                programmes = list(executor.map(add_deadlines, programmes))
        self.catalogue_diagnostics += (
            f", applicationPages={'available' if probe_html else 'blocked'}"
        )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages = {1}
    for link in soup.select('a[href*="page="]'):
        query = parse_qs(urlsplit(str(link.get("href", ""))).query)
        for value in query.get("page", []):
            if value.isdigit():
                pages.add(int(value))
    return max(pages)


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes: list[DiscoveredProgramme] = []
    for item in soup.select("li.search-results__accordion-item"):
        title_link = item.select_one("a.search-results__accordion-title")
        code_node = item.select_one(".search-results__accordion-code")
        if title_link is None or code_node is None:
            continue
        code = _normalise_text(code_node.get_text(" ", strip=True))
        full_title = _normalise_text(title_link.get_text(" ", strip=True))
        title = (
            full_title[: -len(code)].strip()
            if full_title.endswith(code)
            else full_title
        )
        qualification = _table_value(item, "Qualification type")
        if qualification not in TAUGHT_QUALIFICATIONS or not re.match(
            r"^(?:Executive\s+)?Master(?:'s)?\b", title, re.I
        ):
            continue
        course_path = str(title_link.get("href", "")).split("?", 1)[0]
        course_slug = course_path.rstrip("/").rsplit("/", 1)[-1].lower()
        if not course_slug:
            continue
        handbook_url = f"{CANONICAL_HANDBOOK_ORIGIN}/2026/courses/{course_slug}"
        marketing_url = (
            f"{STUDY_ORIGIN}/find/courses/graduate/{_slug(title)}/how-to-apply/"
        )
        programmes.append(
            DiscoveredProgramme(
                id=f"melbourne-{_slug(title)}-{course_slug}",
                name=title,
                degree_type="Master",
                faculty="",
                department="",
                source_url=handbook_url,
                application_url=marketing_url,
                windows=[],
                deadline_text=(
                    "The official University of Melbourne Handbook confirms this "
                    f"{qualification.lower()} course. Application dates are "
                    "course-specific and were not available from the application "
                    "page during this run."
                ),
                parse_status="no-deadline",
            )
        )
    return programmes


def _table_value(item, heading: str) -> str:
    for row in item.select("table tr"):
        label = row.select_one("th")
        value = row.select_one("td")
        if (
            label is not None
            and value is not None
            and _normalise_text(label.get_text(" ", strip=True)).lower()
            == heading.lower()
        ):
            return _normalise_text(value.get_text(" ", strip=True))
    return ""


def _add_course_deadlines(
    programme: DiscoveredProgramme,
    html: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    text = _normalise_text(soup.get_text(" ", strip=True))
    windows: list[DiscoveredWindow] = []
    for match in DEADLINE_RE.finditer(text):
        deadline = _date(match.group("date"))
        intake_label = _normalise_text(match.group("intake"))
        windows.append(
            DiscoveredWindow(
                round=(
                    "Start year deadline"
                    if intake_label.lower().startswith("start")
                    else "Mid-year deadline"
                ),
                applicant_categories=["domestic"],
                opens_at=None,
                closes_at=deadline,
                intake=_intake(intake_label, deadline),
                source_url=programme.application_url,
            )
        )
    windows = list(
        {(window.round, window.closes_at): window for window in windows}.values()
    )
    if not windows:
        return programme
    first_match = DEADLINE_RE.search(text)
    excerpt = text[max(0, first_match.start() - 140) : first_match.end() + 180]
    return replace(
        programme,
        windows=sorted(windows, key=lambda item: item.closes_at),
        deadline_text=excerpt[:1200],
        parse_status="incomplete",
    )


def _intake(label: str, deadline: str) -> str:
    parsed = date.fromisoformat(deadline)
    if label.lower().startswith("start"):
        return f"Semester 1 {parsed.year + 1}"
    return f"Semester 2 {parsed.year}"


def _date(value: str) -> str:
    parsed = datetime.strptime(value.title(), "%d %B %Y")
    return date(parsed.year, parsed.month, parsed.day).isoformat()


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
