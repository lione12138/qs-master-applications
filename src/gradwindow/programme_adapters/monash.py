from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

UNIVERSITY_ID = "monash-university"
CATALOG_URL = "https://handbook.monash.edu/sitemap.xml"
APPLICATION_URL = "https://www.monash.edu/admissions/apply/international-pg"
HANDBOOK_COURSE_RE = re.compile(
    r"^https://handbook\.monash\.edu/2026/courses/(?P<code>[A-Za-z]6\d{3})/?$"
)
MASTER_TITLE_RE = re.compile(
    r"^(?P<code>[A-Za-z]6\d{3})\s+-\s+(?P<title>Master(?:'s)?\s+of\s+.+?)\s+-\s+Monash University$",
    re.I,
)
DEADLINE_RE = re.compile(
    r"(?P<round>(?:Round\s+\d+|timely|final)?\s*applications?)\s+"
    r"(?:are\s+)?(?:close|closing|due)(?:\s+on|\s+by)?\s*:?[ \t]*"
    r"(?P<date>\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+20\d{2})",
    re.I,
)
OPENING_RE = re.compile(
    r"applications?\s+(?:are\s+)?open(?:ing)?(?:\s+on)?\s*:?[ \t]*"
    r"(?P<date>\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+20\d{2})",
    re.I,
)
MARKETING_PROBE_URL = (
    "https://www.monash.edu/study/courses/find-a-course/business-analytics-b6022"
)


class MonashAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"

    def __init__(
        self,
        minimum_expected_programmes: int = 90,
        *,
        detail_workers: int = 10,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers
        self.catalogue_diagnostics = "not inspected"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        sitemap_urls = _sitemap_locations(fetcher(self.catalog_url))

        def fetch_sitemap(url: str) -> str:
            try:
                return fetcher(url)
            except Exception:
                return ""

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            sitemap_payloads = list(executor.map(fetch_sitemap, sitemap_urls))
        handbook_urls = sorted(
            {
                url
                for payload in sitemap_payloads
                for url in _sitemap_locations(payload)
                if HANDBOOK_COURSE_RE.match(url)
            }
        )
        self.catalogue_diagnostics = (
            f"childSitemaps={len(sitemap_urls)}, "
            f"readableSitemaps={sum(bool(item) for item in sitemap_payloads)}, "
            f"handbook6000Courses={len(handbook_urls)}"
        )

        def parse_handbook(url: str) -> DiscoveredProgramme | None:
            try:
                return _parse_handbook_programme(url, fetcher(url))
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = [
                programme
                for programme in executor.map(parse_handbook, handbook_urls)
                if programme is not None
            ]
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Monash Handbook only produced "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}. "
                f"Diagnostics: {self.catalogue_diagnostics}"
            )

        marketing_probe = None
        try:
            marketing_probe = fetcher(MARKETING_PROBE_URL)
        except Exception:
            pass
        if marketing_probe:
            probe_id = "monash-master-of-business-analytics-b6022"

            def add_marketing(programme: DiscoveredProgramme) -> DiscoveredProgramme:
                try:
                    html = (
                        marketing_probe
                        if programme.id == probe_id
                        else fetcher(programme.source_url)
                    )
                    return _add_marketing_deadlines(programme, html)
                except Exception:
                    return programme

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.detail_workers
            ) as executor:
                programmes = list(executor.map(add_marketing, programmes))
        self.catalogue_diagnostics += (
            f", confirmedMasters={len(programmes)}, "
            f"marketingPages={'available' if marketing_probe else 'blocked'}"
        )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _sitemap_locations(xml: str) -> list[str]:
    if not xml.strip():
        return []
    root = ElementTree.fromstring(xml)
    return [
        (node.text or "").strip().split("?", 1)[0].rstrip("/")
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1].lower() == "loc" and (node.text or "").strip()
    ]


def _parse_handbook_programme(
    handbook_url: str,
    html: str,
) -> DiscoveredProgramme | None:
    soup = BeautifulSoup(html, "html.parser")
    title_text = _normalise_text(
        soup.title.get_text(" ", strip=True) if soup.title else ""
    )
    title_match = MASTER_TITLE_RE.match(title_text)
    if title_match is None:
        return None
    title = title_match.group("title").replace("Master's of", "Master of")
    code = title_match.group("code").upper()
    text = _normalise_text(soup.get_text(" ", strip=True))
    if not re.search(r"Monash course type:\s+Masters? degree", text, re.I):
        return None
    faculty_match = re.search(
        r"Managing faculty:\s*(?P<faculty>.+?)\s+(?:Credit points:|Full time duration:)",
        text,
        re.I,
    )
    marketing_url = _marketing_url(title, code)
    return DiscoveredProgramme(
        id=f"monash-{_slug(title)}-{code.lower()}",
        name=title,
        degree_type="Master",
        faculty=(
            _normalise_text(faculty_match.group("faculty")) if faculty_match else ""
        ),
        department="",
        source_url=marketing_url,
        application_url=APPLICATION_URL,
        windows=[],
        deadline_text=(
            "Official Monash Handbook confirms this coursework master's course. "
            "No exact application deadline was available from the admissions page."
        ),
        parse_status="no-deadline",
    )


def _marketing_url(title: str, code: str) -> str:
    base = re.sub(r"^Master(?:'s)?\s+of\s+", "", title, flags=re.I)
    return (
        "https://www.monash.edu/study/courses/find-a-course/"
        f"{_slug(base)}-{code.lower()}"
    )


def _add_marketing_deadlines(
    programme: DiscoveredProgramme,
    html: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    text = _normalise_text(soup.get_text(" ", strip=True))
    opening_match = OPENING_RE.search(text)
    opens_at = _date(opening_match.group("date")) if opening_match else None
    windows: list[DiscoveredWindow] = []
    for match in DEADLINE_RE.finditer(text):
        context = text[max(0, match.start() - 260) : match.end() + 80]
        windows.append(
            DiscoveredWindow(
                round=_normalise_text(match.group("round")).capitalize(),
                applicant_categories=["all"],
                opens_at=opens_at,
                closes_at=_date(match.group("date")),
                intake=_intake(context),
                source_url=programme.source_url,
            )
        )
    unique = {(window.round, window.closes_at): window for window in windows}
    windows = sorted(unique.values(), key=lambda item: item.closes_at)
    if not windows:
        return programme
    first_match = DEADLINE_RE.search(text)
    excerpt = (
        text[max(0, first_match.start() - 220) : first_match.end() + 180]
        if first_match
        else programme.deadline_text
    )
    return replace(
        programme,
        windows=windows,
        deadline_text=excerpt[:1200],
        parse_status="parsed"
        if all(item.opens_at for item in windows)
        else "incomplete",
    )


def _intake(context: str) -> str:
    year_match = re.search(r"20\d{2}\s+intake|intake\s+20\d{2}", context, re.I)
    year = (
        int(re.search(r"20\d{2}", year_match.group()).group()) if year_match else 2027
    )
    if re.search(r"Semester\s+(?:two|2)|mid[- ]year", context, re.I):
        return f"Semester 2 {year}"
    return f"Semester 1 {year}"


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
