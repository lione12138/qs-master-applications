from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "mcgill-university"
SITEMAP_URL = "https://www.mcgill.ca/gradapplicants/sitemap.xml"
CYCLE_URL = (
    "https://www.mcgill.ca/importantdates/channels/event/"
    "application-period-admission-september-2027-graduate-studies-361690"
)
APPLICATION_URL = "https://www.mcgill.ca/gradapplicants/apply"
EXISTING_COMPUTER_SCIENCE_ID = "mcgill-computer-science-msc-thesis"

_EXCLUDED_URL_MARKERS = ("-phd", "-grad-cert", "-grad-dip")
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
_MONTH_DAY_RE = re.compile(rf"(?P<month>{_MONTHS})\s+(?P<day>\d{{1,2}})", re.I)
_FRENCH_MONTHS = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}
_FRENCH_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>"
    + "|".join(_FRENCH_MONTHS)
    + r")(?:\s+(?P<year>20\d{2}))?",
    re.I,
)
_FULL_DATE_RE = re.compile(
    rf"(?P<month>{_MONTHS})\s+(?P<day>\d{{1,2}}),\s+(?P<year>20\d{{2}})",
    re.I,
)


class McGillAdapter(BaseProgrammeAdapter):
    """Discover McGill master's programs and current Fall deadline tables."""

    university_id = UNIVERSITY_ID
    catalog_url = SITEMAP_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 155,
        workers: int = 8,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.workers = workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        intake_year, cycle_opens_at = _fall_cycle(_fetch_with_retry(fetcher, CYCLE_URL))
        candidate_urls = _candidate_urls(_fetch_with_retry(fetcher, SITEMAP_URL))
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            pages = list(
                executor.map(partial(_fetch_with_retry, fetcher), candidate_urls)
            )
        records = [
            record
            for url, html in zip(candidate_urls, pages, strict=True)
            if (record := _programme_record(url, html)) is not None
        ]
        title_counts = Counter(record["title"] for record in records)
        non_thesis_titles = {
            record["title"] for record in records if "-non-thesis" in record["slug"]
        }
        programmes = [
            _programme(
                record,
                intake_year=intake_year,
                cycle_opens_at=cycle_opens_at,
                duplicate_title=title_counts[record["title"]] > 1,
                has_non_thesis_track=record["title"] in non_thesis_titles,
            )
            for record in records
        ]
        programmes.sort(key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "McGill's official sitemap only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        self.intake = f"Fall {intake_year}"
        return DiscoveredCatalog(
            application_opens_at=cycle_opens_at,
            programmes=programmes,
        )


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


def _fall_cycle(html: str) -> tuple[int, str]:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    intake_match = re.search(r"admission in September\s+(20\d{2})", text, re.I)
    dates = list(_FULL_DATE_RE.finditer(text))
    if intake_match is None or len(dates) < 2:
        raise ValueError("McGill's official Fall 2027 application period was not found")
    intake_year = int(intake_match.group(1))
    opens_at = _full_date(dates[0])
    closes_at = _full_date(dates[1])
    if opens_at != f"{intake_year - 1}-09-15" or closes_at[:4] != str(intake_year):
        raise ValueError(
            "McGill's official Fall 2027 application period was inconsistent"
        )
    return intake_year, opens_at


def _candidate_urls(xml: str) -> list[str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("McGill graduate-program sitemap was invalid") from exc
    urls = []
    for node in root.iter():
        if not node.tag.endswith("loc") or not node.text:
            continue
        url = node.text.strip()
        parsed = urlparse(url)
        lowered = parsed.path.lower()
        if (
            parsed.hostname != "www.mcgill.ca"
            or "/gradapplicants/program/" not in lowered
            or any(marker in lowered for marker in _EXCLUDED_URL_MARKERS)
        ):
            continue
        urls.append(parsed._replace(scheme="https", query="", fragment="").geturl())
    urls = sorted(set(urls))
    if not urls:
        raise ValueError("McGill sitemap did not contain graduate programme pages")
    return urls


def _programme_record(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    if heading is None:
        raise ValueError(f"McGill programme page did not contain a title: {url}")
    title = _normalise(heading.get_text(" ", strip=True))
    degree_type = _degree_type(title)
    if degree_type is None:
        return None
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].lower()
    description = _program_description(soup)
    department, faculty = _academic_unit(description)
    return {
        "url": url,
        "slug": slug,
        "title": title,
        "degree_type": degree_type,
        "department": department,
        "faculty": faculty,
        "deadline_table": _deadline_table(soup),
        "document_text": _normalise(soup.get_text(" ", strip=True)),
    }


def _degree_type(title: str) -> str | None:
    if title.lower().startswith("msca "):
        return "MScA"
    if title.lower().startswith("master") or title.lower().startswith(
        "international masters"
    ):
        matches = re.findall(r"\(([^()]+)\)", title)
        return next(
            (value for value in matches if _master_abbreviation(value)),
            "Master",
        )
    for value in re.findall(r"\(([^()]+)\)", title):
        if _master_abbreviation(value):
            return value
    return None


def _master_abbreviation(value: str) -> bool:
    compact = re.sub(r"[^A-Za-z]", "", value).upper()
    return compact.startswith("M") or compact in {"STM", "IMHL"}


def _program_description(soup: BeautifulSoup) -> str:
    heading = next(
        (
            node
            for node in soup.find_all("h2")
            if _normalise(node.get_text(" ", strip=True)) == "Program Description"
        ),
        None,
    )
    paragraph = heading.find_next("p") if heading is not None else None
    return _normalise(paragraph.get_text(" ", strip=True)) if paragraph else ""


def _academic_unit(description: str) -> tuple[str, str]:
    match = re.search(
        r"offered by the (?P<department>.+?) in the (?P<faculty>.+?) is\b",
        description,
        re.I,
    )
    if match is None:
        return "", "McGill University"
    department = _normalise(match.group("department")).rstrip(" ,;")
    faculty = _normalise(match.group("faculty")).rstrip(" ,;")
    if (
        len(department) > 80
        or len(faculty) > 60
        or not faculty.lower().startswith("faculty of ")
    ):
        return "", "McGill University"
    return department, faculty


def _deadline_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        headers = [
            _normalise(cell.get_text(" ", strip=True)).lower()
            for cell in table.select("tr:first-of-type th")
        ]
        if all(
            any(_header_matches(header, kind) for header in headers)
            for kind in ("open", "international", "domestic")
        ):
            return table
    return None


def _programme(
    record: dict,
    *,
    intake_year: int,
    cycle_opens_at: str,
    duplicate_title: bool,
    has_non_thesis_track: bool,
) -> DiscoveredProgramme:
    slug = record["slug"]
    programme_id = f"mcgill-{slug}"
    is_non_thesis = "-non-thesis" in slug
    if duplicate_title and has_non_thesis_track and not is_non_thesis:
        programme_id += "-thesis"
    if slug == "computer-science-msc":
        programme_id = EXISTING_COMPUTER_SCIENCE_ID

    name = record["title"]
    if is_non_thesis and "non-thesis" not in name.lower():
        name += " (Non-Thesis)"
    elif duplicate_title and has_non_thesis_track and "thesis" not in name.lower():
        name += " (Thesis)"
    if programme_id == EXISTING_COMPUTER_SCIENCE_ID:
        name = "MSc in Computer Science (Thesis)"

    windows, deadline_text = _fall_windows(
        record["deadline_table"],
        source_url=record["url"],
        intake_year=intake_year,
        cycle_opens_at=cycle_opens_at,
    )
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=record["degree_type"],
        faculty=record["faculty"],
        department=record["department"],
        source_url=record["url"],
        application_url=APPLICATION_URL,
        windows=windows,
        deadline_text=deadline_text,
        parse_status="parsed" if windows else "no-deadline",
        retrieval_method="official-page",
        evidence_quality="official-full-text",
        evidence_document_hash=hashlib.sha256(
            record["document_text"].encode("utf-8")
        ).hexdigest(),
    )


def _fall_windows(
    table,
    *,
    source_url: str,
    intake_year: int,
    cycle_opens_at: str,
) -> tuple[list[DiscoveredWindow], str]:
    if table is None:
        return [], (
            f"McGill lists this master's programme, but its page does not publish "
            f"an application-deadline table for Fall {intake_year}."
        )
    rows = table.find_all("tr")
    if not rows:
        return [], f"No application deadline was published for Fall {intake_year}."
    headers = [
        _normalise(cell.get_text(" ", strip=True)).lower()
        for cell in rows[0].find_all(["th", "td"])
    ]
    indexes = {
        "intake": _header_index(headers, "intake"),
        "open": _header_index(headers, "open"),
        "international": _header_index(headers, "international"),
        "domestic": _header_index(headers, "domestic"),
    }
    fall_values = None
    for row in rows[1:]:
        cells = [
            _normalise(cell.get_text(" ", strip=True)) for cell in row.find_all("td")
        ]
        if len(cells) <= max(indexes.values()):
            continue
        intake_text = cells[indexes["intake"]].upper()
        if intake_text.startswith("FALL") or intake_text.startswith("AUTOMNE"):
            fall_values = cells
            break
    if fall_values is None:
        return [], f"No Fall {intake_year} intake row was published."

    open_text = fall_values[indexes["open"]]
    opens_at = _cycle_date(open_text, intake_year)
    windows = []
    for category in ("international", "domestic"):
        closes_at = _cycle_date(
            fall_values[indexes[category]],
            intake_year,
            not_before=opens_at,
        )
        if opens_at is None or closes_at is None:
            continue
        if opens_at > closes_at:
            raise ValueError(
                f"McGill {category} deadline precedes its opening date: {source_url}"
            )
        windows.append(
            DiscoveredWindow(
                round=f"Fall {category} deadline",
                applicant_categories=[category],
                opens_at=opens_at,
                closes_at=closes_at,
                intake=f"Fall {intake_year}",
                source_url=source_url,
            )
        )
    row_text = " | ".join(fall_values)
    if windows:
        return windows, (
            f"McGill's official programme table lists Fall {intake_year}: "
            f"{row_text}. The official Fall cycle opens on {cycle_opens_at}."
        )
    return [], (
        f"McGill's official programme table lists no complete Fall {intake_year} "
        f"application window: {row_text}."
    )


def _header_index(headers: list[str], label: str) -> int:
    try:
        return next(
            index
            for index, header in enumerate(headers)
            if _header_matches(header, label)
        )
    except StopIteration as exc:
        raise ValueError(f"McGill deadline table omitted the {label!r} column") from exc


def _header_matches(header: str, kind: str) -> bool:
    if kind == "intake":
        return "intake" in header or "période" in header
    if kind == "open":
        return "applications open" in header or "applications ouvertes" in header
    is_deadline = "deadline" in header or "limite" in header
    if kind == "international":
        return is_deadline and "international" in header
    if kind == "domestic":
        return is_deadline and any(
            marker in header for marker in ("domestic", "canadien", "résident")
        )
    return False


def _cycle_date(
    value: str,
    intake_year: int,
    *,
    not_before: str | None = None,
) -> str | None:
    full_match = _FULL_DATE_RE.search(value)
    if full_match is not None:
        return _full_date(full_match)
    match = _MONTH_DAY_RE.search(value)
    if match is not None:
        month = datetime.strptime(match.group("month"), "%B").month
        day = int(match.group("day"))
    else:
        french_match = _FRENCH_DATE_RE.search(value)
        if french_match is None:
            return None
        month = _FRENCH_MONTHS[french_match.group("month").lower()]
        day = int(french_match.group("day"))
        if french_match.group("year"):
            return (
                datetime(int(french_match.group("year")), month, day).date().isoformat()
            )
    if not_before is not None:
        candidates = [
            datetime(year, month, day).date().isoformat()
            for year in range(intake_year - 2, intake_year + 1)
        ]
        return next(
            (candidate for candidate in candidates if candidate >= not_before),
            None,
        )
    year = intake_year - 1 if month >= 7 else intake_year
    return datetime(year, month, day).date().isoformat()


def _full_date(match: re.Match) -> str:
    return (
        datetime.strptime(
            f"{match.group('month')} {match.group('day')} {match.group('year')}",
            "%B %d %Y",
        )
        .date()
        .isoformat()
    )


def _normalise(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
