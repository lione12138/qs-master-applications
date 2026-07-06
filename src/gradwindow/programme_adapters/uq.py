from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from dataclasses import replace
from datetime import date
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

UNIVERSITY_ID = "the-university-of-queensland"
CATALOG_URL = "https://study.uq.edu.au/sitemap.xml"
APPLICATION_URL = "https://apply.uq.edu.au/"
BASE_URL = "https://study.uq.edu.au"
INTAKE_YEAR = 2026
APPLICATION_OPENS_AT = "2025-08-01"

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
MONTH_DAY_RE = re.compile(
    rf"(?P<month>{MONTHS})\s+(?P<day>\d{{1,2}})\s+"
    rf"of\s+the\s+(?P<year_ref>previous\s+year|year\s+of\s+commencement)",
    flags=re.IGNORECASE,
)
PROGRAM_LINK_RE = re.compile(
    r"<loc>(https://study\.uq\.edu\.au/study-options/programs/master-[^<]+)</loc>"
)
SITEMAP_PAGE_RE = re.compile(
    r"<loc>(https://study\.uq\.edu\.au/sitemap\.xml\?page=\d+)</loc>"
)


class UQAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "inferred-cycle-default"
    intake = "Semester 1 2026"

    def __init__(
        self,
        minimum_expected_programmes: int = 80,
        *,
        detail_workers: int = 6,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        sitemap_pages = SITEMAP_PAGE_RE.findall(fetcher(self.catalog_url))
        programmes: dict[str, DiscoveredProgramme] = {}
        for page_url in sitemap_pages:
            for url in PROGRAM_LINK_RE.findall(fetcher(page_url)):
                clean_url = url.split("?", 1)[0]
                slug = urlparse(clean_url).path.rstrip("/").split("/")[-1]
                if "/" in slug or not slug.startswith("master-"):
                    continue
                programme_id = f"uq-{_slug(slug)}"
                programmes[programme_id] = DiscoveredProgramme(
                    id=programme_id,
                    name=_title_from_slug(slug),
                    degree_type="Master",
                    faculty="",
                    department="",
                    source_url=clean_url,
                    application_url=self.application_url,
                    windows=[],
                    deadline_text="Programme found in UQ's official sitemap.",
                    parse_status="no-deadline",
                )
        values = sorted(programmes.values(), key=lambda item: item.id)
        if len(values) < self.minimum_expected_programmes:
            raise ValueError(
                f"UQ sitemap only contained {len(values)} master programmes; "
                f"expected at least {self.minimum_expected_programmes}"
            )

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return self._parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        "Programme found in UQ's official sitemap, but the detail "
                        f"page could not be fetched: {type(exc).__name__}: "
                        f"{str(exc)[:180]}"
                    ),
                    parse_status="no-deadline",
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, values))
        return DiscoveredCatalog(
            application_opens_at=APPLICATION_OPENS_AT, programmes=detailed
        )

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
    ) -> DiscoveredProgramme:
        soup = BeautifulSoup(html, "html.parser")
        title = _page_title(soup) or programme.name
        windows: list[DiscoveredWindow] = []
        excerpts: list[str] = []
        for section in soup.select("section[data-student-type]"):
            heading = _normalise_text(
                " ".join(h.get_text(" ", strip=True) for h in section.find_all("h3"))
            )
            section_text = _normalise_text(section.get_text(" ", strip=True))
            if "Important dates" not in heading:
                continue
            if "The closing date for this program is" not in section_text:
                continue
            category = section.get("data-student-type")
            applicant_categories = (
                ["international-students"]
                if category == "international"
                else ["domestic-students"]
            )
            excerpts.append(section_text)
            for semester, closes_at in _parse_closing_dates(section_text):
                windows.append(
                    DiscoveredWindow(
                        round=semester,
                        closes_at=closes_at,
                        applicant_categories=applicant_categories,
                        opens_at=None,
                        intake=f"{semester} 2026",
                    )
                )
        return replace(
            programme,
            id=_programme_id(title, programme.source_url),
            name=title,
            windows=_dedupe_windows(windows),
            deadline_text=" ".join(excerpts)[:1600]
            if excerpts
            else programme.deadline_text,
            parse_status="parsed" if windows else "no-deadline",
        )


def _parse_closing_dates(text: str) -> list[tuple[str, str]]:
    windows: list[tuple[str, str]] = []
    for sentence in re.split(r"(?<=\.)\s+|(?=To commence study)", text):
        if "To commence study" not in sentence:
            continue
        semester_match = re.search(r"semester\s+(?P<semester>[12])", sentence, re.I)
        date_match = MONTH_DAY_RE.search(sentence)
        if semester_match is None or date_match is None:
            continue
        year = (
            INTAKE_YEAR - 1
            if "previous" in date_match.group("year_ref").lower()
            else INTAKE_YEAR
        )
        month = datetime_month(date_match.group("month"))
        day = int(date_match.group("day"))
        windows.append(
            (
                f"Semester {semester_match.group('semester')}",
                date(year, month, day).isoformat(),
            )
        )
    return windows


def datetime_month(value: str) -> int:
    import datetime as _datetime

    return _datetime.datetime.strptime(value.capitalize(), "%B").month


def _dedupe_windows(windows: list[DiscoveredWindow]) -> list[DiscoveredWindow]:
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    deduped: list[DiscoveredWindow] = []
    for window in windows:
        key = (window.round, window.closes_at, tuple(window.applicant_categories))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(window)
    return deduped


def _page_title(soup: BeautifulSoup) -> str | None:
    heading = soup.find("h1")
    if heading is not None:
        text = _normalise_text(heading.get_text(" ", strip=True))
        text = re.sub(r"\s*-\s*2026\s*$", "", text)
        if text:
            return text
    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        return _normalise_text(str(meta["content"]).split(" - Study", 1)[0])
    return None


def _programme_id(title: str, source_url: str) -> str:
    slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
    code_match = re.search(r"-(\d+)$", slug)
    code = code_match.group(1) if code_match else ""
    base = re.sub(r"^Master of\s+", "", title, flags=re.I)
    suffix = f"-{code}" if code else ""
    return f"uq-{_slug(base)}-master{suffix}"


def _title_from_slug(slug: str) -> str:
    title = re.sub(r"-\d+$", "", slug)
    return " ".join(part.capitalize() for part in title.split("-"))


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
