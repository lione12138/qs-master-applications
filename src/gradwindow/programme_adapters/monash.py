from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

UNIVERSITY_ID = "monash-university"
CATALOG_URL = "https://www.monash.edu/sitemap.xml"
APPLICATION_URL = "https://www.monash.edu/admissions/apply/international-pg"
DEFAULT_INTAKE = "Semester 1 2027"
COURSE_PATH_RE = re.compile(
    r"^/study/courses/find-a-course/(?P<slug>[^/]+)-(?P<code>[a-zA-Z]\d{4})/?$"
)
MASTER_MARKER_RE = re.compile(r"\bMaster(?:'s|’s) degree\b", re.I)
MASTER_NAME_RE = re.compile(
    r"\b(?:The\s+)?(?P<name>Master of [A-Z][^.\n]{2,120}?)\s+"
    r"(?:is|offers|provides|equips|prepares|has)\b"
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


class MonashAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"

    def __init__(
        self,
        minimum_expected_programmes: int = 50,
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
        urls = _candidate_urls(fetcher(self.catalog_url))
        self.catalogue_diagnostics = f"candidate6000CourseUrls={len(urls)}"

        def parse_one(url: str) -> DiscoveredProgramme | None:
            try:
                return _parse_programme(url, fetcher(url))
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = [
                programme
                for programme in executor.map(parse_one, urls)
                if programme is not None
            ]
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Monash official sitemap/detail pages only produced "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}. "
                f"Diagnostics: {self.catalogue_diagnostics}"
            )
        self.catalogue_diagnostics += f", confirmedMasters={len(programmes)}"
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _candidate_urls(xml: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    urls: set[str] = set()
    for node in root.iter():
        if (
            node.tag.rsplit("}", 1)[-1].lower() != "loc"
            or not (node.text or "").strip()
        ):
            continue
        url = (node.text or "").strip().split("?", 1)[0].rstrip("/")
        match = COURSE_PATH_RE.match(urlsplit(url).path)
        if match is None or int(match.group("code")[1:]) < 6000:
            continue
        urls.add(url)
    return sorted(urls)


def _parse_programme(url: str, html: str) -> DiscoveredProgramme | None:
    soup = BeautifulSoup(html, "html.parser")
    text = _normalise_text(soup.get_text(" ", strip=True))
    if MASTER_MARKER_RE.search(text) is None:
        return None
    path_match = COURSE_PATH_RE.match(urlsplit(url).path)
    if path_match is None:
        return None
    code = path_match.group("code").upper()
    title = _programme_name(soup, text, path_match.group("slug"))
    windows = _parse_windows(text, url)
    faculty = _faculty(soup, text)
    return DiscoveredProgramme(
        id=f"monash-{_slug(title)}-{code.lower()}",
        name=title,
        degree_type="Master",
        faculty=faculty,
        department="",
        source_url=url,
        application_url=APPLICATION_URL,
        windows=windows,
        deadline_text=(
            _deadline_excerpt(text)
            if windows
            else (
                "Official Monash course page confirms this master's degree, but "
                "does not publish an exact application deadline."
            )
        ),
        parse_status="incomplete" if windows else "no-deadline",
    )


def _programme_name(soup: BeautifulSoup, text: str, slug: str) -> str:
    name_match = MASTER_NAME_RE.search(text)
    if name_match is not None:
        return _clean_name(name_match.group("name"))
    meta = soup.find("meta", property="og:title")
    candidates = []
    if meta and meta.get("content"):
        candidates.append(str(meta["content"]))
    heading = soup.find("h1")
    if heading is not None:
        candidates.append(heading.get_text(" ", strip=True))
    for candidate in candidates:
        candidate = re.split(r"\s+[-|]\s+", _normalise_text(candidate), maxsplit=1)[0]
        candidate = re.sub(r"\s+[A-Z]\d{4}$", "", candidate).strip()
        if candidate:
            if candidate.lower().startswith("master"):
                return _clean_name(candidate)
            return f"Master of {candidate}"
    fallback = re.sub(r"-[a-z]\d{4}$", "", slug, flags=re.I)
    return "Master of " + _title_from_slug(fallback)


def _parse_windows(text: str, source_url: str) -> list[DiscoveredWindow]:
    opening_match = OPENING_RE.search(text)
    opens_at = _date(opening_match.group("date")) if opening_match else None
    windows: list[DiscoveredWindow] = []
    for match in DEADLINE_RE.finditer(text):
        context = text[max(0, match.start() - 260) : match.end() + 80]
        intake = _intake(context)
        round_label = _normalise_text(match.group("round")).capitalize()
        windows.append(
            DiscoveredWindow(
                round=round_label,
                applicant_categories=["all"],
                opens_at=opens_at,
                closes_at=_date(match.group("date")),
                intake=intake,
                source_url=source_url,
            )
        )
    unique: dict[tuple[str, str], DiscoveredWindow] = {}
    for window in windows:
        unique[(window.round, window.closes_at)] = window
    return sorted(unique.values(), key=lambda item: item.closes_at)


def _intake(context: str) -> str:
    year_match = re.search(r"20\d{2}\s+intake|intake\s+20\d{2}", context, re.I)
    year = (
        int(re.search(r"20\d{2}", year_match.group()).group()) if year_match else 2027
    )
    if re.search(r"Semester\s+(?:two|2)|mid[- ]year", context, re.I):
        return f"Semester 2 {year}"
    return f"Semester 1 {year}"


def _faculty(soup: BeautifulSoup, text: str) -> str:
    for key in ("course:faculty", "faculty"):
        meta = soup.find("meta", attrs={"name": key})
        if meta and meta.get("content"):
            return _normalise_text(str(meta["content"]))
    match = re.search(
        r"Managing faculty\s+([^|]{3,100}?)(?:\s+Study|\s+Contact|$)", text, re.I
    )
    return _normalise_text(match.group(1)) if match else ""


def _deadline_excerpt(text: str) -> str:
    match = DEADLINE_RE.search(text)
    if match is None:
        return "Exact course-specific application deadline found."
    return text[max(0, match.start() - 220) : match.end() + 180][:1200]


def _date(value: str) -> str:
    parsed = datetime.strptime(value.title(), "%d %B %Y")
    return date(parsed.year, parsed.month, parsed.day).isoformat()


def _clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,:;-")


def _title_from_slug(value: str) -> str:
    lowercase = {"and", "for", "in", "of", "the", "to", "with"}
    words = []
    for index, word in enumerate(value.split("-")):
        words.append(
            word.lower() if index and word.lower() in lowercase else word.capitalize()
        )
    return " ".join(words)


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
