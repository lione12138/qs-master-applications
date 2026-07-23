from __future__ import annotations

import concurrent.futures
import html as html_module
import json
import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "technical-university-of-munich"
CATALOG_URL = (
    "https://www.tum.de/en/studies/degree-programs?tx_solr%5Bq%5D=&graduation=Master"
)
APPLICATION_URL = (
    "https://www.tum.de/en/studies/application/"
    "application-info-portal/online-application"
)
EXISTING_INFORMATICS_ID = "tum-informatics-msc"

DEGREE_TYPES = {
    "Master of Science (M.Sc.)": "MSc",
    "Master of Education (M.Ed.)": "MEd",
    "Master of Arts (M.A.)": "MA",
    "Master of Business Administration (MBA)": "MBA",
    "Master of Advanced Studies (MAS)": "MAS",
}

_EXACT_WINDOW_RE = re.compile(
    r"(?P<intake>(?:Winter|Summer)\s+semester\s+20\d{2}(?:/\d{2})?)"
    r"\s*:\s*"
    r"(?P<opens>\d{2}\.\d{2}\.20\d{2})\s*[–—-]\s*"
    r"(?P<closes>\d{2}\.\d{2}\.20\d{2})",
    re.IGNORECASE,
)


class TUMAdapter(BaseProgrammeAdapter):
    """Discover TUM master's programmes and exact year-specific windows."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Varies by programme and semester"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 110,
        detail_workers: int = 8,
        minimum_detail_success_ratio: float = 0.9,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers
        self.minimum_detail_success_ratio = minimum_detail_success_ratio

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_html = fetcher(CATALOG_URL)
        page_count = _page_count(first_html)
        page_html = [first_html]
        if page_count > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.detail_workers, page_count - 1)
            ) as executor:
                page_html.extend(
                    executor.map(
                        fetcher,
                        [catalog_page_url(page) for page in range(2, page_count + 1)],
                    )
                )

        programmes_by_url: dict[str, DiscoveredProgramme] = {}
        for page in page_html:
            for programme in _catalogue_programmes(page):
                programmes_by_url[programme.source_url] = programme
        programmes = sorted(programmes_by_url.values(), key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "TUM official master catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )

        def parse_one(
            programme: DiscoveredProgramme,
        ) -> tuple[DiscoveredProgramme, bool]:
            try:
                return _parse_detail(programme, fetcher(programme.source_url)), True
            except Exception as exc:
                return (
                    replace(
                        programme,
                        deadline_text=(
                            "Official TUM programme page could not be checked during "
                            f"discovery: {type(exc).__name__}: {str(exc)[:180]}"
                        ),
                        retrieval_method="official-tum-catalogue-detail-fetch-error",
                    ),
                    False,
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            parsed = list(executor.map(parse_one, programmes))
        successful_details = sum(success for _, success in parsed)
        minimum_successes = math.ceil(
            len(programmes) * self.minimum_detail_success_ratio
        )
        if successful_details < minimum_successes:
            raise ValueError(
                "TUM detail-page discovery only checked "
                f"{successful_details} of {len(programmes)} programmes; "
                f"expected at least {minimum_successes}"
            )
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=[programme for programme, _ in parsed],
        )


def catalog_page_url(page: int) -> str:
    return (
        "https://www.tum.de/en/studies/degree-programs?"
        f"tx_solr%5Bpage%5D={page}&tx_solr%5Bq%5D=&graduation=Master"
    )


def _page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages = [1]
    for link in soup.select('nav[aria-label="pagebrowser"] a[href]'):
        match = re.search(r"tx_solr%5Bpage%5D=(\d+)", str(link.get("href", "")))
        if match:
            pages.append(int(match.group(1)))
    return max(pages)


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for article in soup.select("#studycourselist-174899 article.list-teaser"):
        heading = article.select_one("h3")
        degree = article.select_one(".roofline")
        link = article.select_one('a[href*="/en/studies/degree-programs/detail/"]')
        if heading is None or degree is None or link is None:
            continue
        name = _normalise(heading.get_text(" ", strip=True))
        degree_label = _normalise(degree.get_text(" ", strip=True))
        degree_type = DEGREE_TYPES.get(degree_label)
        source_url = _programme_url(str(link.get("href", "")))
        if not name or degree_type is None or source_url is None:
            continue
        url_slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
        programme_id = f"tum-{_slug(url_slug)}"
        if url_slug == "informatics-master-of-science-msc":
            programme_id = EXISTING_INFORMATICS_ID
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=f"{degree_type} {name}",
                degree_type=degree_type,
                faculty="Technical University of Munich",
                department="",
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    "Programme found in TUM's official filtered master catalogue; "
                    "the official detail page has not yet been checked."
                ),
                parse_status="no-deadline",
                retrieval_method="official-tum-master-catalogue-and-detail-page",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _parse_detail(
    programme: DiscoveredProgramme,
    html: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    course = _course_json_ld(soup)
    deadline = _normalise(course.get("applicationDeadline", ""))
    application_url = _application_url(course) or APPLICATION_URL
    faculty_link = soup.select_one(
        ".flex__lg-3 .in2studyfinder.no-js .ce-textmedia--aside h2 a[href]"
    )
    faculty = (
        _normalise(faculty_link.get_text(" ", strip=True))
        if faculty_link is not None
        else programme.faculty
    )
    windows = _exact_windows(deadline, programme.source_url)
    if windows:
        deadline_text = deadline
        parse_status = "parsed"
    elif deadline:
        deadline_text = (
            f"Official TUM application period: {deadline} The page does not "
            "publish a cycle year with both exact dates, so no application "
            "window is inferred."
        )
        parse_status = "no-deadline"
    else:
        deadline_text = (
            "The current official TUM programme page does not publish an "
            "application period."
        )
        parse_status = "no-deadline"
    return replace(
        programme,
        faculty=faculty,
        application_url=application_url,
        windows=windows,
        deadline_text=deadline_text,
        parse_status=parse_status,
    )


def _course_json_ld(soup: BeautifulSoup) -> dict:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        payloads = payload if isinstance(payload, list) else [payload]
        for item in payloads:
            if not isinstance(item, dict):
                continue
            types = item.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "Course" in types:
                return item
    raise ValueError("official TUM detail page did not contain Course JSON-LD")


def _application_url(course: dict) -> str | None:
    action = course.get("potentialAction")
    if not isinstance(action, dict):
        return None
    target = action.get("target")
    if not isinstance(target, dict):
        return None
    value = str(target.get("urlTemplate", ""))
    parsed = urlparse(value)
    if parsed.scheme == "https" and (
        parsed.hostname == "www.tum.de" or parsed.hostname == "tum.de"
    ):
        return value
    return None


def _exact_windows(deadline: str, source_url: str) -> list[DiscoveredWindow]:
    windows = []
    for match in _EXACT_WINDOW_RE.finditer(deadline):
        windows.append(
            DiscoveredWindow(
                round="Application period",
                opens_at=_iso_date(match.group("opens")),
                closes_at=_iso_date(match.group("closes")),
                intake=_normalise(match.group("intake")),
                source_url=source_url,
            )
        )
    return windows


def _programme_url(value: str) -> str | None:
    absolute, _fragment = urldefrag(urljoin("https://www.tum.de", value))
    parsed = urlparse(absolute)
    if parsed.hostname not in {"www.tum.de", "tum.de"}:
        return None
    if not parsed.path.startswith("/en/studies/degree-programs/detail/"):
        return None
    return absolute.rstrip("/")


def _iso_date(value: str) -> str:
    return datetime.strptime(value, "%d.%m.%Y").date().isoformat()


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.decode().lower()).strip("-")


def _normalise(value: object) -> str:
    decoded = html_module.unescape(str(value or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", decoded).strip()
