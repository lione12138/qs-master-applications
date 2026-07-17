from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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

UNIVERSITY_ID = "london-school-of-economics-and-political-science-lse"
CATALOG_URL = "https://www.lse.ac.uk/study-at-lse/Graduate/Available-programmes"
APPLICATIONS_URL = (
    "https://www.lse.ac.uk/study-at-lse/Graduate/Prospective-students/"
    "How-to-Apply/When-to-apply"
)
EXPECTED_INTAKE = "2026/27"
FACULTY = "London School of Economics and Political Science"
EXISTING_DATA_SCIENCE_ID = "lse-data-science-msc"
NOT_ACCEPTING_TEXT = "Not accepting applications for 2026 entry"

_MASTER_SECTIONS = (
    "MA/MSc A-G",
    "MA/MSc H-O (including LLM)",
    "MA/MSc P-Z (including MPA, MPP)",
    "Executive Masters Degrees",
    "Double Degrees",
)
_DOUBLE_DEGREES = "Double Degrees"
_OPENING_RE = re.compile(
    r"Applications for entry in (?P<intake>20\d{2}/\d{2}) will open on "
    r"(?P<date>\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
    re.I,
)
_CODE_RE = re.compile(r"^(?:\*NEW\*\s+)?(?P<code>[A-Z0-9]{4})\s+(?P<name>.+)$")
_DATE_RE = re.compile(r"(?P<date>\d{1,2}\s+[A-Za-z]+\s+20\d{2})")
_PARTNER_APPLICATION_RE = re.compile(r"apply\s+(?:via|to|through)\s+(?!lse\b)", re.I)


@dataclass(frozen=True, slots=True)
class _CatalogEntry:
    section: str
    code: str | None
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class _Detail:
    department: str
    deadline: str | None


class LSEAdapter(BaseProgrammeAdapter):
    """Discover LSE master's programmes and programme-level deadline evidence."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    intake = EXPECTED_INTAKE
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 150,
        maximum_expected_programmes: int = 170,
        detail_workers: int = 12,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        opens_at = _opening_date(fetcher(APPLICATIONS_URL))
        entries = _catalog_entries(fetcher(CATALOG_URL))
        if len(entries) < self.minimum_expected_programmes:
            raise ValueError(
                "LSE's official catalogue only contained "
                f"{len(entries)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(entries) > self.maximum_expected_programmes:
            raise ValueError(
                "LSE's official catalogue unexpectedly contained "
                f"{len(entries)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        details = _fetch_details(entries, fetcher, workers=self.detail_workers)
        programmes = [
            _programme(entry, details[entry.url], opens_at) for entry in entries
        ]
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("LSE official catalogue generated duplicate programme IDs")
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _opening_date(html: str) -> str:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    match = _OPENING_RE.search(text)
    if match is None or match.group("intake") != EXPECTED_INTAKE:
        raise ValueError(
            f"LSE application page lacked the exact {EXPECTED_INTAKE} opening date"
        )
    return _parse_date(match.group("date"))


def _catalog_entries(html: str) -> list[_CatalogEntry]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for section in _MASTER_SECTIONS:
        heading = next(
            (
                item
                for item in soup.select("h2")
                if _normalise(item.get_text(" ", strip=True)) == section
            ),
            None,
        )
        table = heading.find_next("table") if heading is not None else None
        if heading is None or table is None:
            raise ValueError(f"LSE catalogue lacked the {section} table")
        for row in table.select("tr"):
            cell = row.select_one("td")
            link = cell.select_one("a[href]") if cell is not None else None
            if link is None:
                continue
            row_text = _normalise(cell.get_text(" ", strip=True))
            match = _CODE_RE.match(row_text)
            code = match.group("code") if match else None
            name = _normalise(match.group("name") if match else row_text)
            url = _official_programme_url(urljoin(CATALOG_URL, str(link["href"])))
            entries.append(_CatalogEntry(section, code, name, url))
    return entries


def _fetch_details(entries: list[_CatalogEntry], fetcher, *, workers: int) -> dict:
    urls = sorted({entry.url for entry in entries})
    details = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetcher, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                details[url] = _detail(future.result(), url)
            except Exception as exc:
                raise ValueError(
                    f"LSE programme detail fetch failed for {url}: {exc}"
                ) from exc
    return details


def _detail(html: str, url: str) -> _Detail:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("h1") is None:
        raise ValueError(f"LSE programme detail lacked a heading: {url}")
    department_node = soup.select_one(".super-tag--department")
    department = (
        _normalise(department_node.get_text(" ", strip=True))
        if department_node is not None
        else FACULTY
    )
    deadline = _label_value(soup, "Application deadline")
    academic_year = _label_value(soup, "Academic year")
    if academic_year not in {None, EXPECTED_INTAKE, NOT_ACCEPTING_TEXT}:
        raise ValueError(
            f"LSE programme detail reported academic year {academic_year}: {url}"
        )
    return _Detail(department=department, deadline=deadline)


def _label_value(soup: BeautifulSoup, label_text: str) -> str | None:
    label = next(
        (
            item
            for item in soup.select(".label")
            if _normalise(item.get_text(" ", strip=True)) == label_text
        ),
        None,
    )
    value = label.find_next_sibling() if label is not None else None
    return _normalise(value.get_text(" ", strip=True)) if value is not None else None


def _programme(
    entry: _CatalogEntry,
    detail: _Detail,
    opens_at: str,
) -> DiscoveredProgramme:
    windows, parse_status = _windows(entry, detail.deadline, opens_at)
    deadline = detail.deadline or "No application deadline field is published."
    return DiscoveredProgramme(
        id=_programme_id(entry),
        name=entry.name,
        degree_type=_degree_type(entry.name),
        faculty=FACULTY,
        department=detail.department,
        source_url=entry.url,
        application_url=entry.url,
        windows=windows,
        deadline_text=(
            f"LSE's official {EXPECTED_INTAKE} catalogue lists this programme. "
            f"Its official programme page states: {deadline} "
            f"LSE's central application page states that applications opened on "
            f"{opens_at}. Partner-managed deadlines are not paired with that LSE "
            "opening date."
        ),
        parse_status=parse_status,
        retrieval_method="official-catalogue-and-programme-detail-html",
        evidence_quality="official-full-text",
    )


def _windows(
    entry: _CatalogEntry,
    deadline: str | None,
    opens_at: str,
) -> tuple[list[DiscoveredWindow], str]:
    if deadline is None:
        return [], "no-deadline"
    folded = deadline.lower().replace("–", "-").replace("—", "-")
    if folded.startswith("none - rolling admissions") or folded.startswith(
        "not accepting applications"
    ):
        return [], "no-deadline"
    date_matches = list(_DATE_RE.finditer(deadline))
    if not date_matches:
        return [], "no-deadline"
    partner_managed = (
        entry.section == _DOUBLE_DEGREES
        and "apply via lse" not in folded
        and _PARTNER_APPLICATION_RE.search(deadline) is not None
    )
    if partner_managed:
        return [], "incomplete"

    windows = []
    seen = set()
    segments = [item.strip() for item in deadline.split(";")]
    for segment in segments:
        if "pre-register" in segment.lower():
            continue
        for match in _DATE_RE.finditer(segment):
            closes_at = _parse_date(match.group("date"))
            if closes_at in seen or date.fromisoformat(closes_at) <= date.fromisoformat(
                opens_at
            ):
                continue
            seen.add(closes_at)
            windows.append(
                DiscoveredWindow(
                    round=_round_name(segment, len(date_matches)),
                    opens_at=opens_at,
                    closes_at=closes_at,
                    intake=f"September {EXPECTED_INTAKE.split('/', 1)[0]}",
                    applicant_categories=["all"],
                    source_url=entry.url,
                )
            )
    return (windows, "parsed") if windows else ([], "incomplete")


def _round_name(segment: str, total_dates: int) -> str:
    round_match = re.search(r"\bRound\s+\d+", segment, re.I)
    if round_match:
        return round_match.group(0).title()
    if "early application deadline" in segment.lower():
        return "Early application deadline"
    return "Main deadline" if total_dates == 1 else "Application deadline"


def _programme_id(entry: _CatalogEntry) -> str:
    if entry.code == "G3U1":
        return EXISTING_DATA_SCIENCE_ID
    slug = re.sub(r"[^a-z0-9]+", "-", entry.name.lower()).strip("-")
    return f"lse-{entry.code.lower()}-{slug}" if entry.code else f"lse-{slug}"


def _degree_type(name: str) -> str:
    if re.search(r"\bMSc\b", name, re.I):
        return "MSc"
    if re.search(r"\bMPA\b|Master of Public Administration", name, re.I):
        return "MPA"
    if re.search(r"\bMPP\b|Master of Public Policy", name, re.I):
        return "MPP"
    if re.search(r"\bLLM\b|Master of Laws", name, re.I):
        return "LLM"
    if re.search(r"\bMBA\b", name, re.I):
        return "MBA"
    if re.search(r"\bMA\b", name):
        return "MA"
    return "Master"


def _official_programme_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "www.lse.ac.uk"
        or not parsed.path.lower().startswith("/study-at-lse/graduate/")
    ):
        raise ValueError(
            f"LSE catalogue contained a non-official programme URL: {value}"
        )
    return urlunsplit(("https", "www.lse.ac.uk", parsed.path.rstrip("/"), "", ""))


def _parse_date(value: str) -> str:
    for pattern in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"LSE page contained an invalid date: {value}")


def _normalise(value: object) -> str:
    return " ".join(
        str(value or "").replace("\xa0", " ").replace("\u202f", " ").split()
    )
