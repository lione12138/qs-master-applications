from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-birmingham"
CATALOG_URL = "https://www.birmingham.ac.uk/study/postgraduate/taught/course-search"
APPLICATION_URL = "https://www.birmingham.ac.uk/study/postgraduate/taught/apply"
DEFAULT_INTAKE = "September 2026"

POSTGRADUATE_ID = "e2ad4c71-7518-45d7-b1a2-c1280513496c"
TAUGHT_ID = "a6575da0-f868-4842-bbd8-288437f56505"
MASTERS_ID = "9af0f287-d32f-4daf-8ce3-c75e14bac00b"

CATALOG_FIELDS = (
    "sys.id",
    "sys.uri",
    "entryTitle",
    "courseName",
    "searchDataTitle",
    "qualification",
    "academicLevel1",
    "courseStructure",
    "courseVariation",
    "studyPattern",
    "campus1",
    "deliveryFormat",
    "courseYearDetails",
    "academicStructure",
    "primarySubjectArea",
    "applyUrl",
    "applyUrlSource",
    "startDate",
)
YEAR_FIELDS = (
    "sys.id",
    "entryTitle",
    "title",
    "yearOfEntry",
    "startDate",
    "homeApplicationProcessComposer",
    "internationalApplicationProcessComposer",
)
SHARED_FIELDS = (
    "sys.id",
    "entryTitle",
    "title",
    "description",
    "components",
)

MASTER_DEGREE_RE = re.compile(
    r"\b(?P<degree>MSc|MA|MRes|MEd|LLM|MBA|MPH|MPA|MPP|MMus|MArch|"
    r"MFA|MClin\s+Res|Master(?:'s)?(?:\s+of)?)\b",
    re.I,
)
FULL_DATE_RE = re.compile(
    r"\b(?P<date>\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+20\d{2})\b",
    re.I,
)
MONTH_YEAR_RE = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?P<year>20\d{2})\b",
    re.I,
)
PROGRAMME_ID_ALIASES = {
    "/study/postgraduate/subjects/business-and-management-courses/mba": (
        "birmingham-master-of-business-administration-full-time-uk"
    ),
}


@dataclass(frozen=True, slots=True)
class _CourseRecord:
    programme: DiscoveredProgramme
    year_ids: tuple[str, ...]
    start_date: str


class BirminghamAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"
    replace_pending_candidates = True
    intake = DEFAULT_INTAKE

    def __init__(
        self,
        minimum_expected_programmes: int = 300,
        batch_size: int = 20,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.batch_size = batch_size

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalogue_html = fetcher(CATALOG_URL)
        startup_url = _startup_url(catalogue_html)
        api_root, project_id, access_token = _api_config(fetcher(startup_url))

        catalogue_payload = _search(
            fetcher,
            api_root,
            project_id,
            access_token,
            _catalogue_where(),
            CATALOG_FIELDS,
            page_size=500,
        )
        records = _catalogue_records(catalogue_payload.get("items", []))
        if len(records) < self.minimum_expected_programmes:
            raise ValueError(
                "University of Birmingham catalogue only contained "
                f"{len(records)} master's programmes with official course URLs; "
                f"expected at least {self.minimum_expected_programmes}"
            )

        year_ids = _unique(year_id for record in records for year_id in record.year_ids)
        year_entries, failed_year_ids = _fetch_entries(
            fetcher,
            api_root,
            project_id,
            access_token,
            year_ids,
            YEAR_FIELDS,
            self.batch_size,
        )
        shared_ids = _unique(
            shared_id
            for entry in year_entries.values()
            for shared_id in _composer_reference_ids(entry)
        )
        shared_entries, failed_shared_ids = _fetch_entries(
            fetcher,
            api_root,
            project_id,
            access_token,
            shared_ids,
            SHARED_FIELDS,
            self.batch_size,
        )

        programmes = [
            _enrich_programme(
                record,
                year_entries,
                shared_entries,
                failed_year_ids,
                failed_shared_ids,
            )
            for record in records
        ]
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _catalogue_where() -> list[dict]:
    return [
        {"field": "sys.contentTypeId", "equalTo": "courses"},
        {"field": "academicLevel1.sys.id", "equalTo": POSTGRADUATE_ID},
        {"field": "courseStructure.sys.id", "equalTo": TAUGHT_ID},
        {"field": "qualification.sys.id", "equalTo": MASTERS_ID},
        {"field": "sys.versionStatus", "equalTo": "published"},
    ]


def _startup_url(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", src=True):
        source = script.get("src", "")
        if re.search(r"/static/startup[^/]*\.js(?:\?|$)", source, re.I):
            return urljoin(CATALOG_URL, source)
    raise ValueError("University of Birmingham startup configuration was not found")


def _api_config(script: str) -> tuple[str, str, str]:
    alias = re.search(r'\bvar\s+alias\s*=\s*"(?P<value>[^"]+)"', script)
    project = re.search(r'\bvar\s+project\s*=\s*"(?P<value>[^"]+)"', script)
    token = re.search(r'\baccessToken\s*:\s*"(?P<value>[^"]+)"', script)
    if token is None:
        token = re.search(r'\bACCESS_TOKEN\s*=\s*"(?P<value>[^"]+)"', script)
    if alias is None or project is None or token is None:
        raise ValueError("University of Birmingham delivery API config is incomplete")
    api_root = f"https://api-{alias.group('value')}.cloud.contensis.com"
    return api_root, project.group("value"), token.group("value")


def _search(
    fetcher: Callable[[str], str],
    api_root: str,
    project_id: str,
    access_token: str,
    where: list[dict],
    fields: tuple[str, ...],
    *,
    page_size: int,
) -> dict:
    params = {
        "where": json.dumps(where, separators=(",", ":")),
        "pageSize": str(page_size),
        "pageIndex": "0",
        "fields": ",".join(fields),
        "accessToken": access_token,
    }
    url = (
        f"{api_root}/api/delivery/projects/{project_id}/entries/search?"
        f"{urlencode(params)}"
    )
    payload = json.loads(fetcher(url))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Birmingham delivery API did not return an item list")
    if payload.get("pageCount", 1) not in {0, 1}:
        raise ValueError("Birmingham delivery API response was unexpectedly paginated")
    return payload


def _fetch_entries(
    fetcher: Callable[[str], str],
    api_root: str,
    project_id: str,
    access_token: str,
    entry_ids: list[str],
    fields: tuple[str, ...],
    batch_size: int,
) -> tuple[dict[str, dict], set[str]]:
    entries: dict[str, dict] = {}
    failed: set[str] = set()
    for batch in _batches(entry_ids, batch_size):
        try:
            payload = _search(
                fetcher,
                api_root,
                project_id,
                access_token,
                [
                    {"field": "sys.id", "in": batch},
                    {"field": "sys.versionStatus", "equalTo": "published"},
                ],
                fields,
                page_size=max(len(batch), 1),
            )
        except Exception:
            failed.update(batch)
            continue
        for entry in payload["items"]:
            entry_id = _entry_id(entry)
            if entry_id:
                entries[entry_id] = entry
        failed.update(set(batch) - set(entries))
    return entries, failed


def _catalogue_records(items: list[dict]) -> list[_CourseRecord]:
    records: dict[str, _CourseRecord] = {}
    for item in items:
        if not _has_reference_title(item.get("qualification"), "Masters"):
            continue
        if not _has_reference_title(item.get("courseStructure"), "Taught"):
            continue
        source_url = _course_url((item.get("sys") or {}).get("uri"))
        name = _normalise(
            item.get("entryTitle")
            or item.get("searchDataTitle")
            or item.get("courseName")
            or ""
        )
        if source_url is None or not name:
            continue
        path = urlsplit(source_url).path.rstrip("/")
        programme_id = PROGRAMME_ID_ALIASES.get(path, f"birmingham-{_slug(name)}")
        structures = [
            _normalise(value.get("name", ""))
            for value in item.get("academicStructure", [])
            if isinstance(value, dict) and value.get("name")
        ]
        faculty = structures[0] if structures else ""
        department = structures[-1] if len(structures) > 1 else faculty
        year_ids = tuple(
            entry_id
            for value in item.get("courseYearDetails", [])
            if (entry_id := _entry_id(value))
        )
        records[source_url] = _CourseRecord(
            programme=DiscoveredProgramme(
                id=programme_id,
                name=name,
                degree_type=_degree_type(name),
                faculty=faculty,
                department=department,
                source_url=source_url,
                application_url=_application_url(item.get("applyUrl")),
                windows=[],
                deadline_text=(
                    "Programme found in the official University of Birmingham "
                    "postgraduate taught Masters catalogue."
                ),
                parse_status="no-deadline",
                retrieval_method="official-api",
                evidence_quality="official-full-text",
            ),
            year_ids=year_ids,
            start_date=_normalise(item.get("startDate") or ""),
        )
    return sorted(records.values(), key=lambda record: record.programme.id)


def _enrich_programme(
    record: _CourseRecord,
    year_entries: dict[str, dict],
    shared_entries: dict[str, dict],
    failed_year_ids: set[str],
    failed_shared_ids: set[str],
) -> DiscoveredProgramme:
    windows: list[DiscoveredWindow] = []
    missing_link = any(year_id in failed_year_ids for year_id in record.year_ids)
    for year_id in record.year_ids:
        year_entry = year_entries.get(year_id)
        if year_entry is None:
            continue
        start_date = _normalise(year_entry.get("startDate") or record.start_date)
        for composer_field, applicant_category in (
            ("homeApplicationProcessComposer", "home"),
            ("internationalApplicationProcessComposer", "international"),
        ):
            for shared_id in _composer_reference_ids(
                year_entry,
                fields=(composer_field,),
            ):
                shared_entry = shared_entries.get(shared_id)
                if shared_entry is None:
                    missing_link = missing_link or shared_id in failed_shared_ids
                    continue
                windows.extend(
                    _shared_windows(
                        shared_entry,
                        applicant_category,
                        start_date,
                        year_entry.get("yearOfEntry"),
                        record.programme.source_url,
                    )
                )
    windows = _deduplicate_windows(windows)
    if windows:
        summary = "; ".join(
            f"{window.round}: {window.closes_at} ({window.intake})"
            for window in windows
        )
        deadline_text = (
            "Official Birmingham course-year application configuration: "
            f"{summary}. No exact application opening date is published."
        )
    elif missing_link:
        deadline_text = (
            "The programme is in the official Masters catalogue, but linked "
            "official application-deadline content could not be retrieved during "
            "this discovery run. No date was inferred."
        )
    else:
        deadline_text = (
            "The current official course-year configuration does not expose an "
            "exact application closing date. No date was inferred."
        )
    return replace(
        record.programme,
        windows=windows,
        deadline_text=deadline_text,
        parse_status="incomplete" if windows else "no-deadline",
    )


def _shared_windows(
    entry: dict,
    applicant_category: str,
    start_date: str,
    year_of_entry,
    source_url: str,
) -> list[DiscoveredWindow]:
    title = _normalise(entry.get("entryTitle") or entry.get("title") or "")
    windows = []
    for component in entry.get("components", []):
        value = component.get("value") if isinstance(component, dict) else None
        if not isinstance(value, dict):
            continue
        for fact in value.get("factBoxes", []):
            if not isinstance(fact, dict):
                continue
            stat = _normalise(fact.get("stat") or "")
            description = _normalise(fact.get("description") or "")
            source = _normalise(fact.get("source") or "")
            fact_text = _normalise(" ".join((stat, description, source)))
            combined = _normalise(" ".join((title, fact_text)))
            if "application deadline" not in combined.lower():
                continue
            date_match = FULL_DATE_RE.search(combined)
            if date_match is None:
                continue
            closes_at = _iso_date(date_match.group("date"))
            cycle_year = _cycle_year(year_of_entry, start_date, title, closes_at)
            if int(closes_at[:4]) < cycle_year:
                continue
            intake = _intake(fact_text, start_date, cycle_year, closes_at)
            windows.append(
                DiscoveredWindow(
                    round=(
                        "Home applicants"
                        if applicant_category == "home"
                        else "International applicants"
                    ),
                    closes_at=closes_at,
                    applicant_categories=[applicant_category],
                    intake=intake,
                    source_url=source_url,
                )
            )
    return windows


def _deduplicate_windows(windows: list[DiscoveredWindow]) -> list[DiscoveredWindow]:
    grouped: dict[tuple[str, str], set[str]] = {}
    sources: dict[tuple[str, str], str | None] = {}
    for window in windows:
        key = (window.closes_at, window.intake or DEFAULT_INTAKE)
        grouped.setdefault(key, set()).update(window.applicant_categories)
        sources[key] = window.source_url
    result = []
    for (closes_at, intake), categories in grouped.items():
        if categories == {"home", "international"}:
            applicant_categories = ["all"]
            round_name = "Application deadline"
        elif "international" in categories:
            applicant_categories = ["international"]
            round_name = "International applicants"
        else:
            applicant_categories = ["home"]
            round_name = "Home applicants"
        result.append(
            DiscoveredWindow(
                round=round_name,
                closes_at=closes_at,
                applicant_categories=applicant_categories,
                intake=intake,
                source_url=sources[(closes_at, intake)],
            )
        )
    return sorted(result, key=lambda window: (window.closes_at, window.round))


def _composer_reference_ids(
    entry: dict,
    *,
    fields: tuple[str, ...] = (
        "homeApplicationProcessComposer",
        "internationalApplicationProcessComposer",
    ),
) -> list[str]:
    ids = []
    for field in fields:
        for component in entry.get(field, []):
            if not isinstance(component, dict):
                continue
            entry_id = _entry_id(component.get("value") or {})
            if entry_id and entry_id not in ids:
                ids.append(entry_id)
    return ids


def _cycle_year(year_of_entry, start_date: str, title: str, closes_at: str) -> int:
    years = [int(closes_at[:4])]
    for value in (str(year_of_entry or ""), start_date, title):
        years.extend(int(year) for year in re.findall(r"\b20\d{2}\b", value))
    return max(years)


def _intake(
    evidence: str,
    start_date: str,
    cycle_year: int,
    closes_at: str,
) -> str:
    if re.search(r"\bJanuary(?:\s+start|\s+20\d{2})", evidence, re.I):
        explicit = re.search(r"\bJanuary\s+(20\d{2})\b", evidence, re.I)
        year = int(explicit.group(1)) if explicit else int(closes_at[:4]) + 1
        return f"January {year}"
    if re.search(r"\bSeptember(?:\s+start|\s+20\d{2})", evidence, re.I):
        return f"September {cycle_year}"
    match = MONTH_YEAR_RE.search(start_date)
    if match:
        year = max(int(match.group("year")), cycle_year)
        return f"{match.group('month').title()} {year}"
    month = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\b",
        start_date,
        re.I,
    )
    if month:
        return f"{month.group(1).title()} {cycle_year}"
    return f"September {cycle_year}"


def _course_url(uri) -> str | None:
    if not isinstance(uri, str) or not uri.strip():
        return None
    url = urljoin(CATALOG_URL, uri)
    split = urlsplit(url)
    if split.netloc.lower() not in {"birmingham.ac.uk", "www.birmingham.ac.uk"}:
        return None
    if not re.search(r"/(?:study|dubai/study)/postgraduate/", split.path, re.I):
        return None
    return urlunsplit(("https", "www.birmingham.ac.uk", split.path.rstrip("/"), "", ""))


def _application_url(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return APPLICATION_URL
    url = urljoin("https://www.birmingham.ac.uk", value.strip())
    split = urlsplit(url)
    host = split.netloc.lower()
    if not (
        host.endswith(".bham.ac.uk")
        or host == "bham.ac.uk"
        or host.endswith(".birmingham.ac.uk")
        or host == "birmingham.ac.uk"
    ):
        return APPLICATION_URL
    return urlunsplit(("https", split.netloc, split.path, split.query, ""))


def _has_reference_title(values, expected: str) -> bool:
    return isinstance(values, list) and any(
        isinstance(value, dict)
        and _normalise(value.get("entryTitle") or "").lower() == expected.lower()
        for value in values
    )


def _entry_id(value: dict) -> str | None:
    if not isinstance(value, dict):
        return None
    entry_id = (value.get("sys") or {}).get("id")
    return entry_id if isinstance(entry_id, str) and entry_id else None


def _degree_type(name: str) -> str:
    match = MASTER_DEGREE_RE.search(name)
    if match is None:
        return "Master"
    value = re.sub(r"\s+", " ", match.group("degree"))
    known = {
        "msc": "MSc",
        "ma": "MA",
        "mres": "MRes",
        "med": "MEd",
        "llm": "LLM",
        "mba": "MBA",
        "mph": "MPH",
        "mpa": "MPA",
        "mpp": "MPP",
        "mmus": "MMus",
        "march": "MArch",
        "mfa": "MFA",
        "mclin res": "MClin Res",
    }
    return known.get(value.lower(), "Master")


def _iso_date(value: str) -> str:
    clean = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value, flags=re.I)
    return datetime.strptime(clean, "%d %B %Y").date().isoformat()


def _batches(values: list[str], size: int) -> Iterable[list[str]]:
    if size < 1:
        raise ValueError("Birmingham API batch size must be positive")
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )
