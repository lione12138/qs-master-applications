from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "brown-university"
CATALOG_URL = "https://graduateprograms.brown.edu/graduate_programs"

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
_DATE_RE = re.compile(
    rf"(?P<month>{_MONTHS})\s+(?P<day>\d{{1,2}})[,.]?\s+(?P<year>20\d{{2}})",
    re.I,
)
_INTAKE_RE = re.compile(
    r"\b(?P<term>Spring|Summer|Fall|Autumn)\s+(?P<year>20\d{2})\b", re.I
)
_OPENING_RE = re.compile(r"\b(?:Application|App)\s+Opens?\b", re.I)
_INTERNATIONAL_FINAL_RE = re.compile(r"international applicants?.*final deadline", re.I)

_DEGREE_TYPES = {
    "A.M.": "AM",
    "Executive Master": "EMBA",
    "M.Eng.": "MENG",
    "MAT": "MAT",
    "MFA": "MFA",
    "MiM": "MIM",
    "MPA": "MPA",
    "MPH": "MPH",
    "MPP": "MPP",
    "Sc.M.": "SCM",
}


@dataclass(frozen=True, slots=True)
class _CatalogRecord:
    name: str
    degrees: tuple[str, ...]
    source_url: str
    combined_degree: bool


class BrownAdapter(BaseProgrammeAdapter):
    """Discover Brown's central master's catalogue and current official windows."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 46,
        maximum_expected_programmes: int = 52,
        as_of: date | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.as_of = as_of or date.today()

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        records = _catalogue_records(fetcher(CATALOG_URL))
        programmes = []
        for record in records:
            programmes.extend(
                _detail_programmes(record, fetcher(record.source_url), self.as_of)
            )
        programmes = sorted(programmes, key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Brown's official catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "Brown's official catalogue unexpectedly contained "
                f"{len(programmes)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("Brown's official catalogue generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(document: str) -> list[_CatalogRecord]:
    soup = BeautifulSoup(document, "html.parser")
    records = []
    for row in soup.select(".views-row"):
        classifications = _normalise(
            " ".join(
                item.get_text(" ", strip=True) for item in row.select(".term-item")
            )
        )
        if (
            "Master Program" not in classifications
            or "Medical Degree" in classifications
        ):
            continue
        link = row.select_one("h2 a[href]")
        degree_field = row.select_one(
            ".views-field-field-program-degree-type .field-content"
        )
        if link is None or degree_field is None:
            raise ValueError("Brown's master's catalogue contained an incomplete row")
        source_url = _official_programme_url(urljoin(CATALOG_URL, str(link["href"])))
        degrees = tuple(
            _normalise(value)
            for value in degree_field.get_text(" ", strip=True).split(",")
            if _normalise(value)
        )
        unknown = sorted(set(degrees) - set(_DEGREE_TYPES))
        if not degrees or unknown:
            raise ValueError(
                "Brown's master's catalogue contained unsupported degrees: "
                f"{unknown or degrees}"
            )
        name = _normalise(link.get_text(" ", strip=True))
        records.append(
            _CatalogRecord(
                name=name,
                degrees=degrees,
                source_url=source_url,
                combined_degree="Dual Degree" in name,
            )
        )
    if not records:
        raise ValueError("Brown's official master's catalogue was not found")
    return records


def _detail_programmes(
    record: _CatalogRecord,
    document: str,
    as_of: date,
) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(document, "html.parser")
    title = soup.select_one("h1.page_title")
    if title is None or _normalise(title.get_text(" ", strip=True)) != record.name:
        raise ValueError(f"Brown programme page title did not match {record.name}")
    detail_degrees = tuple(
        _normalise(item.get_text(" ", strip=True))
        for item in soup.select(".degree_types .degree_types_title")
    )
    if detail_degrees and set(detail_degrees) != set(record.degrees):
        raise ValueError(f"Brown programme degrees did not match {record.name}")

    faculty_link = soup.select_one(".degrees_info_title_link")
    faculty = (
        _normalise(faculty_link.get_text(" ", strip=True))
        if faculty_link is not None
        else "Brown University"
    )
    apply_link = soup.select_one(".section_break_header_container a.apply[href]")
    if apply_link is None:
        apply_link = soup.select_one("a.apply[href]")
    application_url = (
        _application_url(str(apply_link["href"]))
        if apply_link is not None
        else record.source_url
    )
    windows = _application_windows(soup, record.source_url, as_of)
    fully_exact = bool(windows) and all(window.opens_at for window in windows)
    deadline_text = _deadline_text(record.name, windows)
    evidence_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()

    degree_groups = (
        [record.degrees]
        if record.combined_degree
        else [(degree,) for degree in record.degrees]
    )
    programmes = []
    for degree_group in degree_groups:
        degree_label = "/".join(degree_group)
        degree_type = "/".join(_DEGREE_TYPES[value] for value in degree_group)
        programmes.append(
            DiscoveredProgramme(
                id=_programme_id(record.name, degree_group),
                name=_programme_name(record.name, degree_label, record.combined_degree),
                degree_type=degree_type,
                faculty=faculty,
                department=record.name,
                source_url=record.source_url,
                application_url=application_url,
                windows=[_copy_window(window) for window in windows],
                deadline_text=deadline_text,
                parse_status="parsed" if fully_exact else "incomplete",
                retrieval_method="official-central-programme-page",
                evidence_quality="official-full-text",
                evidence_document_hash=evidence_hash,
            )
        )
    return programmes


def _application_windows(
    soup: BeautifulSoup,
    source_url: str,
    as_of: date,
) -> list[DiscoveredWindow]:
    windows = []
    for paragraph in soup.select("main p"):
        lines = _text_lines(paragraph)
        if not lines:
            continue
        intake_match = _INTAKE_RE.fullmatch(lines[0])
        if intake_match is None:
            continue
        sibling = paragraph.find_next_sibling("p")
        while sibling is not None:
            sibling_lines = _text_lines(sibling)
            if sibling_lines and _INTAKE_RE.fullmatch(sibling_lines[0]):
                break
            lines.extend(sibling_lines)
            sibling = sibling.find_next_sibling("p")
        windows.extend(
            _prose_intake_windows(
                lines,
                _intake_label(intake_match),
                source_url,
                as_of,
            )
        )

    for heading in soup.find_all("h3"):
        if _normalise(heading.get_text(" ", strip=True)) != "Application Deadlines":
            continue
        table = heading.find_next("table")
        if table is not None:
            windows.extend(_table_windows(table, source_url, as_of))

    windows = _deduplicate_windows(windows)
    if not windows:
        windows = _generic_date_windows(soup, source_url, as_of)
    return sorted(windows, key=_window_sort_key)


def _text_lines(element) -> list[str]:
    return [
        _normalise(value)
        for value in element.get_text("\n", strip=True).splitlines()
        if _normalise(value)
    ]


def _prose_intake_windows(
    lines: list[str],
    intake: str,
    source_url: str,
    as_of: date,
) -> list[DiscoveredWindow]:
    opens_at = None
    international_final = None
    deadlines: list[tuple[str, date]] = []
    for line in lines[1:]:
        observed_date = _date_in_text(line)
        if observed_date is None:
            continue
        if _OPENING_RE.search(line):
            opens_at = observed_date
            continue
        if _INTERNATIONAL_FINAL_RE.search(line):
            international_final = observed_date
            continue
        round_label = _deadline_round(line[: _DATE_RE.search(line).start()])
        if round_label is not None:
            deadlines.append((round_label, observed_date))

    windows = []
    for round_label, closes_at in deadlines:
        if closes_at < as_of:
            continue
        if opens_at is not None and opens_at > closes_at:
            raise ValueError(
                f"Brown published an opening after a deadline for {intake}"
            )
        categories = (
            ["domestic-students"]
            if round_label == "Final deadline" and international_final is not None
            else ["all"]
        )
        windows.append(
            _window(
                round_label,
                closes_at,
                intake,
                source_url,
                opens_at,
                categories,
            )
        )
    if international_final is not None and international_final >= as_of:
        if opens_at is not None and opens_at > international_final:
            raise ValueError(
                f"Brown published an opening after an international deadline for {intake}"
            )
        windows.append(
            _window(
                "International final deadline",
                international_final,
                intake,
                source_url,
                opens_at,
                ["international-students"],
            )
        )
    return windows


def _table_windows(table, source_url: str, as_of: date) -> list[DiscoveredWindow]:
    headers = [
        _normalise(cell.get_text(" ", strip=True))
        for cell in table.select("thead tr th")
    ]
    if len(headers) < 2:
        return []
    windows = []
    for row in table.select("tbody tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != len(headers):
            raise ValueError("Brown application deadline table changed columns")
        intake_text = _normalise(cells[0].get_text(" ", strip=True))
        for heading, cell in zip(headers[1:], cells[1:], strict=True):
            if "Fifth-Year" in heading or "Fifth Year" in heading:
                continue
            closes_at = _date_in_text(cell.get_text(" ", strip=True))
            if closes_at is None or closes_at < as_of:
                continue
            intake = _table_intake(intake_text, closes_at)
            if heading == "International Students":
                round_label = "International deadline"
                categories = ["international-students"]
            elif heading == "Final Deadline":
                round_label = "Final deadline"
                categories = (
                    ["domestic-students"]
                    if "International Students" in headers
                    else ["all"]
                )
            else:
                round_label = _deadline_round(heading)
                categories = ["all"]
            if round_label is None:
                continue
            windows.append(
                _window(
                    round_label,
                    closes_at,
                    intake,
                    source_url,
                    None,
                    categories,
                )
            )
    return windows


def _generic_date_windows(
    soup: BeautifulSoup,
    source_url: str,
    as_of: date,
) -> list[DiscoveredWindow]:
    windows = []
    for block in soup.select(".date"):
        heading = block.find(["h3", "h4"])
        time = block.find("time")
        if heading is None or time is None:
            continue
        label = _normalise(heading.get_text(" ", strip=True))
        if "5th Year" in label or "5 th Year" in label:
            continue
        closes_at = _date_in_text(
            str(time.get("datetime", "")) or time.get_text(" ", strip=True)
        )
        if closes_at is None or closes_at < as_of:
            continue
        round_label = _deadline_round(label)
        if round_label is None:
            continue
        windows.append(
            _window(
                round_label,
                closes_at,
                f"{closes_at.year} admission",
                source_url,
                None,
                ["all"],
            )
        )
    return _deduplicate_windows(windows)


def _deadline_round(value: str) -> str | None:
    value = _normalise(value).strip(" :*.-")
    if not value:
        return None
    if re.search(r"\bEarly Action(?: Deadline)?\b", value, re.I):
        return "Early action deadline"
    priority = re.search(
        r"\bPriority(?:\s+Review)?(?:\s+Deadline)?\s*(?P<number>\d+)?(?:\s+Deadline)?\b",
        value,
        re.I,
    )
    if priority:
        number = priority.group("number")
        if "Review" in priority.group(0):
            return f"Priority review {number}" if number else "Priority review"
        return f"Priority {number} deadline" if number else "Priority deadline"
    if re.search(r"\bFinal Deadline\b", value, re.I):
        return "Final deadline"
    if re.search(r"\bApplication Deadline\b", value, re.I):
        return "Application deadline"
    return None


def _table_intake(value: str, closes_at: date) -> str:
    match = _INTAKE_RE.search(value)
    if match is not None:
        return _intake_label(match)
    term_match = re.search(r"\b(Spring|Summer|Fall|Autumn)\b", value, re.I)
    if term_match is None:
        return f"{closes_at.year} admission"
    term = term_match.group(1).title().replace("Autumn", "Fall")
    year = closes_at.year + (term == "Spring" and closes_at.month >= 7)
    return f"{term} {year}"


def _intake_label(match: re.Match[str]) -> str:
    term = match.group("term").title().replace("Autumn", "Fall")
    return f"{term} {match.group('year')}"


def _date_in_text(value: str) -> date | None:
    match = _DATE_RE.search(value)
    if match is None:
        iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", value)
        return date.fromisoformat(iso_match.group(0)) if iso_match else None
    return datetime.strptime(
        f"{match.group('month')} {match.group('day')} {match.group('year')}",
        "%B %d %Y",
    ).date()


def _window(
    round_label: str,
    closes_at: date,
    intake: str,
    source_url: str,
    opens_at: date | None,
    categories: list[str],
) -> DiscoveredWindow:
    return DiscoveredWindow(
        round=round_label,
        opens_at=opens_at.isoformat() if opens_at else None,
        closes_at=closes_at.isoformat(),
        intake=intake,
        applicant_categories=categories,
        source_url=source_url,
    )


def _copy_window(window: DiscoveredWindow) -> DiscoveredWindow:
    return DiscoveredWindow(
        round=window.round,
        opens_at=window.opens_at,
        closes_at=window.closes_at,
        intake=window.intake,
        applicant_categories=list(window.applicant_categories),
        source_url=window.source_url,
    )


def _deduplicate_windows(windows: list[DiscoveredWindow]) -> list[DiscoveredWindow]:
    return list(
        {
            (
                window.intake,
                window.round,
                tuple(window.applicant_categories),
                window.opens_at,
                window.closes_at,
            ): window
            for window in windows
        }.values()
    )


def _window_sort_key(window: DiscoveredWindow) -> tuple:
    round_order = {
        "Early action deadline": 0,
        "Priority review 1": 1,
        "Priority 1 deadline": 1,
        "Priority deadline": 1,
        "Priority review 2": 2,
        "Priority 2 deadline": 2,
        "Priority review 3": 3,
        "Priority 3 deadline": 3,
        "Priority review 4": 4,
        "Priority 4 deadline": 4,
        "Application deadline": 5,
        "Final deadline": 6,
        "International final deadline": 7,
        "International deadline": 7,
    }
    return (
        window.intake or "",
        round_order.get(window.round, 99),
        window.closes_at,
        window.round,
    )


def _programme_id(name: str, degrees: tuple[str, ...]) -> str:
    suffix = "-".join(_DEGREE_TYPES[value].lower() for value in degrees)
    return f"brown-{_slug(name)}-{suffix}"


def _programme_name(name: str, degree: str, combined: bool) -> str:
    if combined or degree == "Executive Master":
        return name
    return f"{degree} in {name}"


def _deadline_text(name: str, windows: list[DiscoveredWindow]) -> str:
    if not windows:
        return (
            f"Brown's official {name} page was checked, but it did not publish an "
            "unexpired application deadline with an exact application opening date."
        )
    exact = sum(bool(window.opens_at) for window in windows)
    if exact == len(windows):
        return (
            f"Brown's official {name} page publishes {len(windows)} current deadline "
            "rounds with exact application opening dates."
        )
    return (
        f"Brown's official {name} page publishes {len(windows)} current deadline "
        "rounds but no exact application opening date for these rounds."
    )


def _official_programme_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname != "graduateprograms.brown.edu"
    ):
        raise ValueError(f"Brown catalogue contained a non-official URL: {value}")
    if not parsed.path.startswith("/graduate-program/"):
        raise ValueError(f"Brown catalogue contained a non-programme URL: {value}")
    return urlunsplit(("https", parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _application_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            f"Brown programme page contained an invalid application URL: {value}"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
