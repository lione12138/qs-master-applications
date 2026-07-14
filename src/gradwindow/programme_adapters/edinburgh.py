from __future__ import annotations

import concurrent.futures
import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

UNIVERSITY_ID = "university-of-edinburgh"
CATALOG_URL = "https://study.ed.ac.uk/programmes/postgraduate-taught"
APPLICATION_GUIDANCE_URL = "https://study.ed.ac.uk/postgraduate/applying/when"
DEFAULT_INTAKE = "September 2026"
RESULTS_PER_PAGE = 10
COURSE_PATH_RE = re.compile(
    r"^/programmes/postgraduate-taught/(?:(?P<edition>20\d{2})/)?"
    r"(?P<code>\d+)-(?P<slug>[^/]+)/?$",
    re.I,
)
DEGREE_RE = re.compile(
    r"\b(?P<degree>MScR|MVetSci|MCouns|MArch|MMus|MFA|MRes|MPhil|MLitt|"
    r"LLM|MBA|MPH|MEd|MFin|MPA|MPP|MSW|MSc|MA|MS|Master)\b",
    re.I,
)
FULL_DATE_TEXT = (
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
    r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+20\d{2}"
)
EXPLICIT_OPEN_RE = re.compile(
    rf"applications?(?:\s+for[^.\n]{{0,80}}?)?\s+"
    rf"(?:will\s+)?open(?:ed)?\s+on\s+(?P<date>{FULL_DATE_TEXT})",
    re.I,
)
EXTENDED_DEADLINE_RE = re.compile(
    rf"(?:application\s+deadline|[‘'\"]?apply\s+by[’'\"]?\s+deadline|"
    rf"round\s+\d+[^.\n]{{0,50}}?application\s+deadline)"
    rf"[^.\n]{{0,80}}?extended\s+to\s+(?P<date>{FULL_DATE_TEXT})",
    re.I,
)
REMAIN_OPEN_RE = re.compile(
    rf"applications?[^.\n]{{0,100}}?remain\s+open[^.\n]{{0,80}}?"
    rf"until\s+(?P<date>{FULL_DATE_TEXT})",
    re.I,
)
START_DATE_RE = re.compile(r"Start date:\s*(?P<month>[A-Z][a-z]+)\s+(?P<year>20\d{2})")
ENTRY_YEAR_RE = re.compile(r"Year of entry:\s*(?P<year>20\d{2})", re.I)


class EdinburghAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_GUIDANCE_URL
    application_opens_at_basis = "missing"
    replace_pending_candidates = True
    intake = DEFAULT_INTAKE

    def __init__(
        self,
        minimum_expected_programmes: int = 250,
        catalogue_workers: int = 6,
        detail_workers: int = 12,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.catalogue_workers = catalogue_workers
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_html = fetcher(CATALOG_URL)
        total = _result_count(first_html)
        page_urls = [
            f"{CATALOG_URL}?page={page}"
            for page in range(1, math.ceil(total / RESULTS_PER_PAGE))
        ]
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.catalogue_workers
        ) as executor:
            remaining_html = list(executor.map(fetcher, page_urls))

        programmes = {}
        for html in [first_html, *remaining_html]:
            for programme in _catalogue_programmes(html):
                programmes[programme.id] = programme
        catalogue = sorted(programmes.values(), key=lambda item: item.id)
        if len(catalogue) < self.minimum_expected_programmes:
            raise ValueError(
                "University of Edinburgh catalogue only contained "
                f"{len(catalogue)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes} from {total} taught results"
            )

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return _parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        "Official programme page could not be checked during "
                        f"discovery: {type(exc).__name__}: {str(exc)[:180]}"
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, catalogue))
        return DiscoveredCatalog(application_opens_at=None, programmes=detailed)


def _result_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    count = soup.select_one("#psw-search-result-count")
    if count and count.get_text(strip=True).isdigit():
        return int(count.get_text(strip=True))
    heading = next(
        (
            item.get_text(" ", strip=True)
            for item in soup.find_all(["h2", "h3"])
            if re.search(r"\bof\s+\d+\s+results\b", item.get_text(" ", strip=True))
        ),
        "",
    )
    match = re.search(r"\bof\s+(?P<count>\d+)\s+results\b", heading)
    if match:
        return int(match.group("count"))
    return len(soup.select("div.result h3 a[href]"))


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for link in soup.select("div.result h3 a[href]"):
        title = _normalise(link.get_text(" ", strip=True))
        source_url = _course_url(link.get("href", ""))
        split = _split_title(title)
        if source_url is None or split is None:
            continue
        base_title, degree_type = split
        if (
            "online-learning" in urlsplit(source_url).path.lower()
            and "online learning" not in base_title.lower()
        ):
            base_title = f"{base_title} (Online Learning)"
        programmes.append(
            DiscoveredProgramme(
                id=f"edinburgh-{_slug(base_title)}-{_slug(degree_type)}",
                name=f"{degree_type} {base_title}",
                degree_type=degree_type,
                faculty="",
                department="",
                source_url=source_url,
                application_url=source_url,
                windows=[],
                deadline_text=(
                    "Programme found in the official University of Edinburgh "
                    "postgraduate taught Degree Finder."
                ),
                parse_status="no-deadline",
                retrieval_method="official-page",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _parse_detail(
    programme: DiscoveredProgramme,
    html: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    school = _key_fact(soup, "School")
    college = _key_fact(soup, "College")
    default_intake, intake_date = _default_intake(soup)
    applying = soup.select_one(".pgt-programme-applying__when")
    if applying is None:
        return replace(
            programme,
            faculty=college,
            department=school,
            deadline_text=(
                "The official programme page does not contain a When to apply "
                "section with an exact application deadline."
            ),
        )

    section_text = _normalise(applying.get_text(" ", strip=True))
    explicit_opening = _explicit_opening(section_text)
    windows = _table_windows(
        applying,
        default_intake=default_intake,
        default_intake_date=intake_date,
        source_url=programme.source_url,
        explicit_opening=explicit_opening,
    )
    windows.extend(
        _extension_windows(
            section_text,
            default_intake=default_intake,
            source_url=programme.source_url,
            opens_at=explicit_opening,
        )
    )
    windows = _deduplicate_windows(windows)
    return replace(
        programme,
        faculty=college,
        department=school,
        windows=windows,
        deadline_text=(
            section_text[:1800]
            if section_text
            else "No exact application deadline was found on the official page."
        ),
        parse_status=(
            "parsed"
            if windows and all(window.opens_at for window in windows)
            else "incomplete"
            if windows
            else "no-deadline"
        ),
    )


def _table_windows(
    applying,
    *,
    default_intake: str,
    default_intake_date: datetime,
    source_url: str,
    explicit_opening: str | None,
) -> list[DiscoveredWindow]:
    windows = []
    for table in applying.select("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"], recursive=False)
        headers = [_normalise(cell.get_text(" ", strip=True)) for cell in header_cells]
        if not any(_deadline_header(header) for header in headers):
            continue
        data_rows = rows[1:]
        close_index = next(
            (index for index, header in enumerate(headers) if _deadline_header(header)),
            None,
        )
        open_index = next(
            (
                index
                for index, header in enumerate(headers)
                if "applications open" in header.lower()
                or "application opens" in header.lower()
            ),
            None,
        )
        start_index = next(
            (
                index
                for index, header in enumerate(headers)
                if "start date" in header.lower()
            ),
            None,
        )
        round_index = next(
            (
                index
                for index, header in enumerate(headers)
                if header.lower() in {"round", "year of entry"}
            ),
            None,
        )
        if close_index is None:
            continue

        for row in data_rows:
            values = [
                _normalise(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"], recursive=False)
            ]
            if close_index >= len(values):
                continue
            intake = default_intake
            row_intake_date = default_intake_date
            if start_index is not None and start_index < len(values):
                parsed_intake = _intake_from_date(values[start_index])
                if parsed_intake is not None:
                    intake, row_intake_date = parsed_intake
            closes_at = _date(values[close_index], row_intake_date)
            if closes_at is None:
                continue
            opens_at = explicit_opening
            if open_index is not None and open_index < len(values):
                opens_at = _date(values[open_index], row_intake_date)
            round_label = "Main application deadline"
            if round_index is not None and round_index < len(values):
                value = values[round_index]
                round_label = (
                    f"{value} entry deadline"
                    if re.fullmatch(r"20\d{2}", value)
                    else f"Round {value}"
                    if value.isdigit()
                    else "Equal consideration deadline"
                    if "year of entry" in headers[round_index].lower()
                    else value
                )
            windows.append(
                DiscoveredWindow(
                    round=round_label,
                    opens_at=opens_at,
                    closes_at=closes_at,
                    intake=intake,
                    source_url=source_url,
                )
            )
    return windows


def _extension_windows(
    text: str,
    *,
    default_intake: str,
    source_url: str,
    opens_at: str | None,
) -> list[DiscoveredWindow]:
    windows = []
    for pattern in (EXTENDED_DEADLINE_RE, REMAIN_OPEN_RE):
        for match in pattern.finditer(text):
            closes_at = _date(match.group("date"), None)
            if closes_at:
                windows.append(
                    DiscoveredWindow(
                        round="Extended application deadline",
                        opens_at=opens_at,
                        closes_at=closes_at,
                        intake=default_intake,
                        source_url=source_url,
                    )
                )
    return windows


def _deduplicate_windows(windows: list[DiscoveredWindow]) -> list[DiscoveredWindow]:
    unique = {}
    for window in windows:
        key = (window.intake, window.opens_at, window.closes_at)
        previous = unique.get(key)
        if previous is None or _round_priority(window.round) > _round_priority(
            previous.round
        ):
            unique[key] = window
    return sorted(
        unique.values(),
        key=lambda item: (item.closes_at, item.round, item.intake or ""),
    )


def _round_priority(value: str) -> int:
    if value == "Extended application deadline":
        return 3
    if value.startswith("Round "):
        return 2
    return 1


def _deadline_header(value: str) -> bool:
    lower = value.lower()
    return (
        "application deadline" in lower
        or "apply by" in lower
        or "equal consideration deadline" in lower
    )


def _explicit_opening(text: str) -> str | None:
    match = EXPLICIT_OPEN_RE.search(text)
    return _date(match.group("date"), None) if match else None


def _default_intake(soup: BeautifulSoup) -> tuple[str, datetime]:
    metadata = soup.select_one(".pgt-programme-metadata__study-options")
    metadata_text = _normalise(metadata.get_text(" ", strip=True)) if metadata else ""
    match = START_DATE_RE.search(metadata_text)
    if match:
        label = f"{match.group('month')} {match.group('year')}"
        return label, datetime.strptime(label, "%B %Y")
    page_text = _normalise(soup.get_text(" ", strip=True))
    entry_match = ENTRY_YEAR_RE.search(page_text)
    year = entry_match.group("year") if entry_match else "2026"
    label = f"September {year}"
    return label, datetime.strptime(label, "%B %Y")


def _intake_from_date(value: str) -> tuple[str, datetime] | None:
    parsed = _datetime(value)
    if parsed is None:
        return None
    return parsed.strftime("%B %Y"), parsed


def _date(value: str, intake_date: datetime | None) -> str | None:
    parsed = _datetime(value)
    if parsed is not None:
        return parsed.date().isoformat()
    if intake_date is None:
        return None
    cleaned = _clean_date(value)
    for date_format in ("%d %B", "%d %b"):
        try:
            partial = datetime.strptime(cleaned, date_format)
        except ValueError:
            continue
        candidate = partial.replace(year=intake_date.year)
        if candidate >= intake_date:
            candidate = candidate.replace(year=intake_date.year - 1)
        return candidate.date().isoformat()
    return None


def _datetime(value: str) -> datetime | None:
    cleaned = _clean_date(value)
    for date_format in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(cleaned, date_format)
        except ValueError:
            continue
    return None


def _clean_date(value: str) -> str:
    cleaned = re.sub(
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b,?",
        "",
        value,
        flags=re.I,
    )
    cleaned = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", cleaned, flags=re.I)
    return _normalise(cleaned.strip(" ,.;"))


def _key_fact(soup: BeautifulSoup, label: str) -> str:
    for item in soup.select(
        ".pgt-programme-metadata__key-facts .pgt-programme-metadata__item"
    ):
        heading = item.find("b")
        if (
            heading
            and _normalise(heading.get_text(" ", strip=True)).lower() == label.lower()
        ):
            value = item.find("p")
            return _normalise(value.get_text(" ", strip=True)) if value else ""
    return ""


def _split_title(value: str) -> tuple[str, str] | None:
    match = DEGREE_RE.search(value)
    if match is None:
        return None
    degree_type = _canonical_degree(match.group("degree"))
    base_title = _normalise(value[: match.start()]) or value
    return base_title, degree_type


def _canonical_degree(value: str) -> str:
    known = {
        "msc": "MSc",
        "mscr": "MScR",
        "mvetsci": "MVetSci",
        "mcouns": "MCouns",
        "march": "MArch",
        "mmus": "MMus",
        "mfa": "MFA",
        "mres": "MRes",
        "mphil": "MPhil",
        "mlitt": "MLitt",
        "llm": "LLM",
        "mba": "MBA",
        "mph": "MPH",
        "med": "MEd",
        "mfin": "MFin",
        "mpa": "MPA",
        "mpp": "MPP",
        "msw": "MSW",
        "ma": "MA",
        "ms": "MS",
        "master": "Master",
    }
    return known[value.lower()]


def _course_url(href: str) -> str | None:
    absolute = urljoin(CATALOG_URL, href)
    parts = urlsplit(absolute)
    if COURSE_PATH_RE.match(parts.path) is None:
        return None
    return urlunsplit(("https", "study.ed.ac.uk", parts.path.rstrip("/"), "", ""))


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())
