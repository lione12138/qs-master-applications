from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from gradwindow.http_client import DEFAULT_USER_AGENT

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "korea-university"
CATALOG_URL = "https://graduate2.korea.ac.kr/department/major.html"
CATALOG_DATA_URL = "https://graduate2.korea.ac.kr/main/ajax_board.html"
SCHEDULE_URL = "https://graduate2.korea.ac.kr/admission/schedule.html"
APPLICATION_URL = "https://graduate2.korea.ac.kr/admission/guide.html"
EXISTING_CS_ID = "korea-university-computer-science-master"
_SCHEDULE_RE = re.compile(
    r"(?P<open_month>[A-Z][a-z]+)\s+(?P<open_day>\d{1,2})\([^)]*\)\s*"
    r"\d{1,2}:\d{2}\s*-\s*(?P<close_month>[A-Z][a-z]+)\s*"
    r"(?P<close_day>\d{1,2})\([^)]*\)\s*\d{1,2}:\d{2},\s*"
    r"(?P<year>20\d{2})"
)


class KoreaAdapter(BaseProgrammeAdapter):
    """Discover Korea University Graduate School master's departments."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2026 international admission"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 95,
        catalog_payload_fetcher: Callable[[], str] | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.catalog_payload_fetcher = catalog_payload_fetcher or _fetch_catalog_html

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        opens_at, closes_at = _schedule_dates(fetcher(SCHEDULE_URL))
        programmes = _programmes(self.catalog_payload_fetcher(), opens_at, closes_at)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Korea University's official directory only contained "
                f"{len(programmes)} master's departments; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _programmes(html: str, opens_at: str, closes_at: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for box in soup.select(".major_box"):
        title_node = box.select_one(".major_tit")
        master_group = _labelled_group(box, "master")
        if title_node is None or master_group is None:
            continue
        department = _normalise(title_node.get_text(" ", strip=True))
        faculty_group = _labelled_group(box, "college")
        faculty = (
            _normalise(faculty_group.get_text(" ", strip=True))
            if faculty_group is not None
            else "Korea University Graduate School"
        )
        source_link = box.select_one("a.major_btn.home[href]")
        source_url = (
            str(source_link.get("href", "")) if source_link is not None else CATALOG_URL
        )
        if source_url.startswith("http://"):
            source_url = "https://" + source_url.removeprefix("http://")
        if not _is_official(source_url):
            source_url = CATALOG_URL
        programme_id = f"korea-university-{_slugify(department)}-master"
        if department == "Department of Computer Science and Engineering":
            programme_id = EXISTING_CS_ID
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=f"Master's Programme in {department}",
                degree_type="Master",
                faculty=faculty,
                department=department,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    "Korea University's official international schedule publishes "
                    f"a general online application period from {opens_at} to "
                    f"{closes_at}. The separate applicable-departments notice can "
                    "change the eligible scope, so the dates remain guidance until "
                    "that scope is deterministically mapped; no programme window is "
                    "inferred."
                ),
                parse_status="no-deadline",
                retrieval_method="official-graduate-school-directory-ajax",
                evidence_quality="official-full-text",
            )
        )
    counts: dict[str, int] = {}
    for programme in programmes:
        counts[programme.id] = counts.get(programme.id, 0) + 1
    for programme in programmes:
        if counts[programme.id] > 1:
            programme.id = f"{programme.id.removesuffix('-master')}-{_slugify(programme.faculty)}-master"
    return sorted(
        programmes, key=lambda programme: (programme.department, programme.faculty)
    )


def _labelled_group(box, label: str):
    for group in box.select(".group"):
        heading = group.select_one(".major_sub_tit")
        if heading is None or label not in heading.get_text(" ", strip=True).lower():
            continue
        value = group.select_one("ul")
        return value
    return None


def _schedule_dates(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    period = None
    for row in soup.select("tr"):
        heading = row.find("th")
        if (
            heading
            and _normalise(heading.get_text(" ", strip=True)) == "Online Application"
        ):
            period = row.find("td")
            break
    match = _SCHEDULE_RE.search(period.get_text(" ", strip=True) if period else "")
    if match is None:
        raise ValueError("Korea University did not publish an exact online schedule")
    year = int(match.group("year"))
    opens_at = datetime.strptime(
        f"{match.group('open_month')} {match.group('open_day')} {year}", "%B %d %Y"
    ).date()
    closes_at = datetime.strptime(
        f"{match.group('close_month')} {match.group('close_day')} {year}", "%B %d %Y"
    ).date()
    return opens_at.isoformat(), closes_at.isoformat()


def _fetch_catalog_html() -> str:
    response = httpx.post(
        CATALOG_DATA_URL,
        data={"mkind": "sch_major_en", "tab": "all", "tbl": "in_bbs_major_en"},
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        timeout=45,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Korea University catalogue endpoint returned no content")
    return content


def _slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _is_official(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host == "korea.ac.kr" or host.endswith(".korea.ac.kr")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
