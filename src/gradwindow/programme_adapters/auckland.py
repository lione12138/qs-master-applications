from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "the-university-of-auckland"
CATALOG_URL = (
    "https://www.auckland.ac.nz/en/study/study-options/find-a-study-option.html"
)
DEADLINES_URL = (
    "https://www.auckland.ac.nz/en/study/applications-and-admissions/how-to-apply/"
    "postgraduate-application-closing-dates.html"
)
APPLICATION_URL = (
    "https://www.auckland.ac.nz/en/study/applications-and-admissions/apply-now.html"
)


def _filtered_url(intake: str) -> str:
    return f"{CATALOG_URL}?programmeType=masters&programmeStartDate={quote(intake)}"


SEMESTER_ONE_2027_URL = _filtered_url("Semester One 2027")
LATE_YEAR_2026_URL = _filtered_url("Late Year Term 2026")

_SEMESTER_ONE_HEADING = "Semester One 2027 application closing dates"
_LATE_YEAR_HEADING = "Late Year 2026 application closing dates"
_SEMESTER_ONE_GENERIC = (
    "International applications for postgraduate sub-doctoral programmes not "
    "otherwise specified"
)
_LATE_YEAR_GENERIC = "All programmes not otherwise specified"
_EXCEPTION_ALIASES = {
    "Master of Health Sciences in Nutrition and Dietetics": (
        "Master of Nutrition and Dietetics"
    ),
}
_YEARLESS_POLICIES = {
    "Master of Organisational Psychology": (
        "open on 22 September",
        "made by 24 November",
    ),
    "Master of Physiotherapy Practice": (
        "open on 1 July",
        "close on 1 October",
    ),
    "Master of Speech Language Therapy Practice": (
        "open on 1 July",
        "made by 1 October",
    ),
}
_EXISTING_IDS = {
    "Master of Data Science": "auckland-data-science-master",
}


@dataclass(frozen=True, slots=True)
class _CatalogRecord:
    name: str
    faculty: str
    source_url: str


class AucklandAdapter(BaseProgrammeAdapter):
    """Discover Auckland master's programmes and scoped official deadlines."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 90,
        maximum_expected_programmes: int = 105,
        minimum_semester_one_programmes: int = 80,
        maximum_semester_one_programmes: int = 90,
        minimum_late_year_programmes: int = 8,
        maximum_late_year_programmes: int = 15,
        as_of: date | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.minimum_semester_one_programmes = minimum_semester_one_programmes
        self.maximum_semester_one_programmes = maximum_semester_one_programmes
        self.minimum_late_year_programmes = minimum_late_year_programmes
        self.maximum_late_year_programmes = maximum_late_year_programmes
        self.as_of = as_of or date.today()

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        catalog_document = fetcher(CATALOG_URL)
        records = _catalogue_records(catalog_document)
        semester_one = _catalogue_records(fetcher(SEMESTER_ONE_2027_URL))
        late_year = _catalogue_records(fetcher(LATE_YEAR_2026_URL))
        _check_count(
            "official catalogue",
            len(records),
            self.minimum_expected_programmes,
            self.maximum_expected_programmes,
        )
        _check_count(
            "Semester One 2027 master's filter",
            len(semester_one),
            self.minimum_semester_one_programmes,
            self.maximum_semester_one_programmes,
        )
        _check_count(
            "Late Year 2026 master's filter",
            len(late_year),
            self.minimum_late_year_programmes,
            self.maximum_late_year_programmes,
        )

        records_by_name = {record.name: record for record in records}
        if len(records_by_name) != len(records):
            raise ValueError("Auckland's official catalogue contained duplicate names")
        _require_subset(records_by_name, semester_one, "Semester One 2027")
        _require_subset(records_by_name, late_year, "Late Year 2026")

        deadline_document = fetcher(DEADLINES_URL)
        semester_rows = _deadline_rows(deadline_document, _SEMESTER_ONE_HEADING)
        late_rows = _deadline_rows(deadline_document, _LATE_YEAR_HEADING)
        if _SEMESTER_ONE_GENERIC not in semester_rows:
            raise ValueError("Auckland's Semester One 2027 generic deadline was absent")
        if _LATE_YEAR_GENERIC not in late_rows:
            raise ValueError("Auckland's Late Year 2026 generic deadline was absent")

        yearless_evidence = {}
        for name, expected_phrases in _YEARLESS_POLICIES.items():
            record = records_by_name.get(name)
            if record is None:
                continue
            document = fetcher(record.source_url)
            text = _normalise(BeautifulSoup(document, "html.parser").get_text(" "))
            for phrase in expected_phrases:
                if phrase.lower() not in text.lower():
                    raise ValueError(
                        f"Auckland's official {name} page changed its yearless policy"
                    )
            yearless_evidence[name] = expected_phrases

        semester_names = {record.name for record in semester_one}
        late_year_names = {record.name for record in late_year}
        programmes = [
            _programme(
                record,
                semester_names=semester_names,
                late_year_names=late_year_names,
                semester_rows=semester_rows,
                late_rows=late_rows,
                yearless_policy=yearless_evidence.get(record.name),
                as_of=self.as_of,
                evidence_document=(catalog_document + deadline_document),
            )
            for record in records
        ]
        programmes.sort(key=lambda item: item.id)
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("Auckland's official catalogue generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(document: str) -> list[_CatalogRecord]:
    soup = BeautifulSoup(document, "html.parser")
    records = []
    for row in soup.select("li.page-listing__item"):
        programme_type = row.select_one("[data-programme-type]")
        if (
            programme_type is None
            or programme_type.get("data-programme-type") != "Masters degree"
        ):
            continue
        heading = row.select_one("[data-programme-name]")
        faculty = row.select_one("[data-programme-faculty]")
        link = row.select_one("a.listing-item__link[href]")
        if heading is None or faculty is None or link is None:
            raise ValueError(
                "Auckland's master's catalogue contained an incomplete row"
            )
        name = _normalise(str(heading.get("data-programme-name", "")))
        records.append(
            _CatalogRecord(
                name=name,
                faculty=_normalise(str(faculty.get("data-programme-faculty", ""))),
                source_url=_official_url(urljoin(CATALOG_URL, str(link["href"]))),
            )
        )
    if not records:
        raise ValueError("Auckland's official master's catalogue was not found")
    return records


def _deadline_rows(document: str, heading_text: str) -> dict[str, date]:
    soup = BeautifulSoup(document, "html.parser")
    heading = next(
        (
            item
            for item in soup.find_all("h2")
            if _normalise(item.get_text(" ", strip=True)) == heading_text
        ),
        None,
    )
    if heading is None:
        raise ValueError(f"Auckland deadline section was not found: {heading_text}")
    table = heading.find_next("table")
    if table is None:
        raise ValueError(f"Auckland deadline table was not found: {heading_text}")
    rows = {}
    for row in table.select("tr")[1:]:
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        name = _normalise(cells[0].get_text(" ", strip=True))
        observed = _parse_date(cells[1].get_text(" ", strip=True))
        if name and observed:
            rows[name] = observed
    if not rows:
        raise ValueError(f"Auckland deadline table was empty: {heading_text}")
    return rows


def _programme(
    record: _CatalogRecord,
    *,
    semester_names: set[str],
    late_year_names: set[str],
    semester_rows: dict[str, date],
    late_rows: dict[str, date],
    yearless_policy: tuple[str, str] | None,
    as_of: date,
    evidence_document: str,
) -> DiscoveredProgramme:
    windows = []
    late_named = late_rows.get(record.name)
    if record.name in late_year_names or late_named is not None:
        closes_at = late_named or late_rows[_LATE_YEAR_GENERIC]
        if closes_at >= as_of:
            windows.append(
                _window(
                    intake="Late Year 2026",
                    closes_at=closes_at,
                    categories=["all"],
                )
            )

    named_semester_deadlines = _named_semester_deadlines(semester_rows)
    named_deadline = named_semester_deadlines.get(record.name)
    if record.name in semester_names:
        if named_deadline is not None:
            if named_deadline >= as_of:
                windows.append(
                    _window(
                        intake="Semester One 2027",
                        closes_at=named_deadline,
                        categories=["all"],
                    )
                )
        elif yearless_policy is None:
            closes_at = semester_rows[_SEMESTER_ONE_GENERIC]
            if closes_at >= as_of:
                windows.append(
                    _window(
                        intake="Semester One 2027",
                        closes_at=closes_at,
                        categories=["international-students"],
                    )
                )

    return DiscoveredProgramme(
        id=_programme_id(record.name),
        name=record.name,
        degree_type="Master",
        faculty=record.faculty,
        department=record.name,
        source_url=record.source_url,
        application_url=APPLICATION_URL,
        windows=windows,
        deadline_text=_deadline_text(
            record.name,
            windows,
            yearless_policy,
            named_deadline,
            as_of,
        ),
        parse_status="incomplete",
        retrieval_method="official-central-catalogue-and-deadline-tables",
        evidence_quality="official-full-text",
        evidence_document_hash=hashlib.sha256(
            evidence_document.encode("utf-8")
        ).hexdigest(),
    )


def _named_semester_deadlines(rows: dict[str, date]) -> dict[str, date]:
    named = {}
    for name, observed in rows.items():
        if name == _SEMESTER_ONE_GENERIC:
            continue
        named[_EXCEPTION_ALIASES.get(name, name)] = observed
    return named


def _window(
    *,
    intake: str,
    closes_at: date,
    categories: list[str],
) -> DiscoveredWindow:
    return DiscoveredWindow(
        round="Application closing date",
        opens_at=None,
        closes_at=closes_at.isoformat(),
        intake=intake,
        applicant_categories=categories,
        source_url=DEADLINES_URL,
    )


def _deadline_text(
    name: str,
    windows: list[DiscoveredWindow],
    yearless_policy: tuple[str, str] | None,
    named_deadline: date | None,
    as_of: date,
) -> str:
    if yearless_policy is not None:
        opening, closing = yearless_policy
        return (
            f"Auckland's official {name} page says applications {opening} and "
            f"{closing} each cycle, but it does not attach a year to those dates; "
            "the policy remains monitoring evidence rather than an exact ISO window."
        )
    if windows:
        return (
            f"Auckland's official deadline tables publish {len(windows)} current "
            f"closing date(s) for {name}, but no exact application opening date."
        )
    if named_deadline is not None and named_deadline < as_of:
        return (
            f"Auckland's official named deadline has passed for {name}; the next "
            "exact application window has not yet been published."
        )
    return (
        f"Auckland's official catalogue lists {name}, but no current exactly dated "
        "application window was published for its configured intake filters."
    )


def _programme_id(name: str) -> str:
    if name in _EXISTING_IDS:
        return _EXISTING_IDS[name]
    short_name = re.sub(r"^Master of\s+", "", name, flags=re.I)
    return f"auckland-{_slug(short_name)}-master"


def _require_subset(
    records_by_name: dict[str, _CatalogRecord],
    subset: list[_CatalogRecord],
    label: str,
) -> None:
    unknown = sorted(
        record.name for record in subset if record.name not in records_by_name
    )
    if unknown:
        raise ValueError(
            f"Auckland {label} filter contained unknown programmes: {unknown}"
        )


def _check_count(label: str, count: int, minimum: int, maximum: int) -> None:
    if count < minimum:
        raise ValueError(
            f"Auckland's {label} only contained {count} master's programmes; "
            f"expected at least {minimum}"
        )
    if count > maximum:
        raise ValueError(
            f"Auckland's {label} unexpectedly contained {count} master's "
            f"programmes; expected at most {maximum}"
        )


def _parse_date(value: str) -> date | None:
    match = re.search(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(20\d{2})\b",
        value,
        re.I,
    )
    if match is None:
        return None
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date()


def _official_url(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        host == "auckland.ac.nz" or host.endswith(".auckland.ac.nz")
    ):
        raise ValueError(f"Auckland catalogue contained a non-official URL: {value}")
    return urlunsplit(("https", parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
