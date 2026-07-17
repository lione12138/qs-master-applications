from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import partial
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "psl-university"
CATALOG_URL = "https://psl.eu/formations?field_niveau%5B30%5D=30"
APPLICATION_URL = (
    "https://psl.eu/formation/admissions/admissions-en-master/candidater-en-master"
)
EXISTING_COMPUTER_SCIENCE_ID = "psl-computer-science-master"
EXISTING_COMPUTER_SCIENCE_URL = "https://psl.eu/formation/master-informatique"

_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS)
_RANGE_RE = re.compile(
    rf"(?:(?:du|de)\s+)?"
    rf"(?P<open_day>\d{{1,2}})(?:er)?\s+"
    rf"(?P<open_month>{_MONTH_PATTERN})"
    rf"(?:\s+(?P<open_year>20\d{{2}}))?\s*"
    rf"(?:au|a|[-–])\s*"
    rf"(?P<close_day>\d{{1,2}})(?:er)?\s+"
    rf"(?P<close_month>{_MONTH_PATTERN})"
    rf"(?:\s+(?P<close_year>20\d{{2}}))?",
    re.I,
)
_APPLICATION_CONTEXT_RE = re.compile(
    r"candidat|depot|dossier|application|postul|session|phase complementaire",
    re.I,
)


class PSLAdapter(BaseProgrammeAdapter):
    """Discover PSL master's and master-grade programmes from its official view."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 55,
        workers: int = 8,
        intake_year: int = 2027,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.workers = workers
        self.intake_year = intake_year
        self.intake = f"Fall {intake_year}"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_page = _fetch_with_retry(fetcher, CATALOG_URL)
        page_count = _page_count(first_page)
        page_urls = [f"{CATALOG_URL}&page={page}" for page in range(1, page_count)]
        with ThreadPoolExecutor(max_workers=min(self.workers, 4)) as executor:
            remaining_pages = list(
                executor.map(partial(_fetch_with_retry, fetcher), page_urls)
            )
        catalogue_pages = [first_page, *remaining_pages]
        records = _catalog_records(catalogue_pages)
        if len(records) < self.minimum_expected_programmes:
            raise ValueError(
                "PSL's official master filter only contained "
                f"{len(records)} programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )

        detail_urls = [record["url"] for record in records]
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            details = list(
                executor.map(partial(_fetch_with_retry, fetcher), detail_urls)
            )
        programmes = [
            _programme(record, html, intake_year=self.intake_year)
            for record, html in zip(records, details, strict=True)
        ]
        programmes.sort(key=lambda item: item.id)
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _fetch_with_retry(
    fetcher: Callable[[str], str],
    url: str,
    attempts: int = 3,
) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetcher(url)
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.25 * (attempt + 1))
    if last_error is None:
        raise ValueError("attempts must be greater than zero")
    raise last_error


def _page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    last_link = soup.select_one("a[rel~=last][href]")
    if last_link is None:
        return 1
    query = parse_qs(urlparse(last_link["href"]).query)
    try:
        return int(query["page"][0]) + 1
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "PSL master catalogue had an invalid last-page link"
        ) from error


def _catalog_records(pages: list[str]) -> list[dict]:
    records: dict[str, dict] = {}
    for html in pages:
        soup = BeautifulSoup(html, "html.parser")
        page_links = soup.select("a.formation_row[href]")
        if not page_links:
            raise ValueError("PSL master catalogue page contained no programme rows")
        for link in page_links:
            url = urljoin("https://psl.eu", link["href"])
            if urlparse(url).netloc not in {"psl.eu", "www.psl.eu"}:
                continue
            records[url] = {
                "url": url.replace("https://www.psl.eu", "https://psl.eu"),
                "catalogue_name": _normalise(link.get_text(" ", strip=True)),
            }
    return list(records.values())


def _programme(record: dict, html: str, *, intake_year: int) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    if heading is None:
        raise ValueError(f"PSL programme page did not contain a title: {record['url']}")
    title = _normalise(heading.get_text(" ", strip=True))
    slug = urlparse(record["url"]).path.rstrip("/").rsplit("/", 1)[-1]
    is_national_master = slug.startswith("master-")
    programme_id = f"psl-{slug}"
    name = f"Master {title}" if is_national_master else title
    degree_type = "Master" if is_national_master else "Grade de master"
    faculty = _operator(record["url"], soup)
    application_url = APPLICATION_URL
    if record["url"] == EXISTING_COMPUTER_SCIENCE_URL:
        programme_id = EXISTING_COMPUTER_SCIENCE_ID
        name = "Master Informatique"
        faculty = "Dauphine-PSL, ENS-PSL and MINES Paris-PSL"
        application_url = "https://www.monmaster.gouv.fr/"

    section_text = _admission_text(soup)
    windows = _application_windows(
        section_text,
        source_url=record["url"],
        intake_year=intake_year,
    )
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=degree_type,
        faculty=faculty,
        department="",
        source_url=record["url"],
        application_url=application_url,
        windows=windows,
        deadline_text=section_text
        or "The official PSL programme page does not publish an admissions calendar.",
        parse_status="parsed" if windows else "no-deadline",
        retrieval_method="official-html",
        evidence_quality="official-full-text",
        evidence_document_hash=hashlib.sha256(html.encode("utf-8")).hexdigest(),
    )


def _operator(source_url: str, soup: BeautifulSoup) -> str:
    for heading in soup.find_all("h3"):
        label = _fold(_normalise(heading.get_text(" ", strip=True))).lower()
        if not label.startswith("etablissement psl operateur"):
            continue
        container = heading.parent
        names = []
        for image in container.select(".etablissement_element img[alt]"):
            name = re.sub(r"^Logo\s+", "", image["alt"], flags=re.I).strip(" ,-")
            if name and name not in names:
                names.append(name)
        return ", ".join(names) or "Université PSL"
    if soup.find("h1") is None:
        raise ValueError(f"PSL programme page did not contain a title: {source_url}")
    return "Université PSL"


def _admission_text(soup: BeautifulSoup) -> str:
    sections = []
    for heading in soup.find_all(["h2", "h3", "h4"]):
        label = _fold(_normalise(heading.get_text(" ", strip=True))).lower()
        if not any(
            marker in label
            for marker in (
                "admission",
                "candidature",
                "modalites et calendrier",
                "quand postuler",
            )
        ):
            continue
        level = int(heading.name[1])
        parts = [_normalise(heading.get_text(" ", strip=True))]
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and re.fullmatch(r"h[1-6]", sibling.name or ""):
                if int(sibling.name[1]) <= level:
                    break
            if isinstance(sibling, Tag):
                text = _normalise(sibling.get_text(" ", strip=True))
                if text:
                    parts.append(text)
        text = _normalise(" ".join(parts))
        if text and text not in sections:
            sections.append(text)
    return _normalise(" ".join(sections))[:4000]


def _application_windows(
    text: str,
    *,
    source_url: str,
    intake_year: int,
) -> list[DiscoveredWindow]:
    folded = _fold(text).lower()
    windows = []
    seen = set()
    for match in _RANGE_RE.finditer(folded):
        context = folded[max(0, match.start() - 100) : match.start()]
        if _APPLICATION_CONTEXT_RE.search(context) is None:
            continue
        open_year = match.group("open_year")
        close_year = match.group("close_year")
        if open_year is None and close_year is None:
            continue
        open_year_number = int(open_year or close_year)
        close_year_number = int(close_year or open_year)
        if close_year_number != intake_year:
            continue
        opens_at = _date(
            open_year_number,
            match.group("open_month"),
            int(match.group("open_day")),
        )
        closes_at = _date(
            close_year_number,
            match.group("close_month"),
            int(match.group("close_day")),
        )
        if opens_at > closes_at:
            continue
        round_label = _round_label(context)
        key = (round_label, opens_at, closes_at)
        if key in seen:
            continue
        seen.add(key)
        windows.append(
            DiscoveredWindow(
                round=f"Fall {intake_year} {round_label}".strip(),
                opens_at=opens_at,
                closes_at=closes_at,
                applicant_categories=["all"],
                intake=f"Fall {intake_year}",
                source_url=source_url,
            )
        )
    windows.sort(key=lambda item: (item.opens_at or "", item.closes_at, item.round))
    return windows


def _round_label(context: str) -> str:
    matches = re.findall(
        r"(session\s+\d+|m[12]|master\s+[12]|phase\s+complementaire)",
        context,
        re.I,
    )
    if not matches:
        return "application period"
    value = matches[-1].lower()
    value = re.sub(r"master\s+", "M", value, flags=re.I)
    return value.replace("phase complementaire", "supplementary phase")


def _date(year: int, month: str, day: int) -> str:
    return date(year, _MONTHS[month.lower()], day).isoformat()


def _fold(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )


def _normalise(value: str) -> str:
    return " ".join(value.replace("\u200b", " ").split())
