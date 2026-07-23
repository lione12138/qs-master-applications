from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from datetime import datetime

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "australian-national-university"
SEARCH_URL = "https://programsandcourses.anu.edu.au/search"
CATALOGUE_API_ROOT = (
    "https://programsandcourses.anu.edu.au/data/ProgramSearch/GetProgramsPostGraduate"
)
INTERNATIONAL_DATES_URL = "https://study.anu.edu.au/apply/international-applications"
APPLICATION_URL = "https://study.anu.edu.au/apply"
EXISTING_COMPUTING_ID = "anu-computing-master"

# These records remain in the postgraduate search endpoint but are not open
# coursework-master applications: MSTD is explicitly an exit award, while the
# MPSC catalogue record no longer exposes an application action.
_NON_APPLICABLE_CODES = {"MSTD", "MPSC"}
_MASTER_RE = re.compile(r"^(?:Executive\s+)?Master\b", re.I)
_SEMESTER_RE = re.compile(
    r"Semester\s+(?P<semester>[12]),\s+(?P<year>20\d{2})\s+"
    r"(?P<body>.*?)(?=Semester\s+[12],\s+20\d{2}|$)",
    re.I,
)
_DATE_TEXT_RE = r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>20\d{2})"


class ANUAdapter(BaseProgrammeAdapter):
    """Discover ANU coursework master's programs and safe deadline guidance."""

    university_id = UNIVERSITY_ID
    catalog_url = SEARCH_URL
    application_url = APPLICATION_URL
    intake = "Current ANU catalogue"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 130) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalogue_year = _latest_catalogue_year(fetcher(SEARCH_URL))
        records = _catalogue_records(
            fetcher(catalogue_api_url(catalogue_year)),
            catalogue_year=catalogue_year,
        )
        guidance = _deadline_guidance(
            fetcher(INTERNATIONAL_DATES_URL),
            catalogue_year=catalogue_year,
        )
        programmes = _programmes(
            records,
            catalogue_year=catalogue_year,
            guidance=guidance,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "ANU's official catalogue only contained "
                f"{len(programmes)} applicable master's programmes; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        self.intake = f"ANU {catalogue_year} catalogue"
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def catalogue_api_url(year: int) -> str:
    return f"{CATALOGUE_API_ROOT}?SelectedYear={year}&PageSize=300&PageIndex=0"


def _latest_catalogue_year(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#programsearchpage[data-searchviewmodel]")
    if container is None:
        raise ValueError("ANU catalogue search metadata was not found")
    try:
        payload = json.loads(container["data-searchviewmodel"])
        years = [
            int(item["Value"])
            for item in payload.get("AvailableYears", [])
            if str(item.get("Value", "")).isdigit()
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("ANU catalogue year metadata was invalid") from exc
    if not years:
        raise ValueError("ANU catalogue did not publish an available academic year")
    return max(years)


def _catalogue_records(payload_text: str, *, catalogue_year: int) -> list[dict]:
    try:
        payload = _catalogue_payload(payload_text)
        items = payload["Items"]
        total_count = int(payload["TotalCount"])
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        ET.ParseError,
    ) as exc:
        raise ValueError("ANU postgraduate catalogue response was invalid") from exc
    if not isinstance(items, list):
        raise ValueError("ANU postgraduate catalogue Items value was not a list")
    if len(items) != total_count:
        raise ValueError(
            f"ANU postgraduate catalogue returned {len(items)} of {total_count} records"
        )

    records = []
    for item in items:
        name = _normalise(item.get("ProgramName", ""))
        code = _normalise(item.get("AcademicPlanCode", "")).upper()
        if (
            not _MASTER_RE.match(name)
            or code in _NON_APPLICABLE_CODES
            or item.get("AcademicCareer") != "Postgraduate"
            or str(item.get("ProgramAcademicYear")) != str(catalogue_year)
        ):
            continue
        if not code:
            raise ValueError(
                "ANU master's catalogue contained a program without a code"
            )
        records.append(
            {
                "code": code,
                "name": name,
                "mode": _normalise(item.get("ModeOfDelivery", "")) or "Unspecified",
            }
        )
    return records


def _catalogue_payload(payload_text: str) -> dict:
    if payload_text.lstrip().startswith("{"):
        return json.loads(payload_text)
    root = ET.fromstring(payload_text)
    item_nodes = [
        node
        for node in root.iter()
        if _local_name(node.tag) == "ProgramSearchResultModel"
    ]
    items = [
        {_local_name(child.tag): child.text or "" for child in node}
        for node in item_nodes
    ]
    total_node = next(
        (node for node in root.iter() if _local_name(node.tag) == "TotalCount"),
        None,
    )
    if total_node is None or total_node.text is None:
        raise ValueError("ANU XML catalogue omitted TotalCount")
    return {"Items": items, "TotalCount": total_node.text}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _deadline_guidance(html: str, *, catalogue_year: int) -> str:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    if "additional selection criteria may vary" not in text.lower():
        raise ValueError(
            "ANU application page omitted its additional-selection exception"
        )

    cycles = []
    for match in _SEMESTER_RE.finditer(text):
        if int(match.group("year")) != catalogue_year:
            continue
        body = match.group("body")
        general_match = re.search(
            rf"will close on the\s+{_DATE_TEXT_RE}",
            body,
            re.I,
        )
        crawford_match = re.search(
            rf"Crawford School.*?(?:is|on)\s+{_DATE_TEXT_RE}",
            body,
            re.I,
        )
        if general_match is None or crawford_match is None:
            # The page repeats semester headings in its table of contents before
            # the full key-date sections.
            continue
        cycles.append(
            (
                int(match.group("semester")),
                _iso_date(general_match),
                _iso_date(crawford_match),
            )
        )
    if {cycle[0] for cycle in cycles} != {1, 2}:
        raise ValueError(
            f"ANU application page did not contain both {catalogue_year} semesters"
        )

    cycle_text = "; ".join(
        f"Semester {semester} general {general}, Crawford {crawford}"
        for semester, general, crawford in sorted(cycles)
    )
    return (
        f"ANU's international application page lists policy guidance for {cycle_text}. "
        "It says applications are now open but publishes no exact opening date, "
        "and warns that application deadlines for programs with additional selection "
        "criteria may vary. These dates are not assigned to individual programmes "
        "without programme-specific confirmation."
    )


def _iso_date(match: re.Match) -> str:
    return (
        datetime.strptime(
            f"{match.group('day')} {match.group('month')} {match.group('year')}",
            "%d %B %Y",
        )
        .date()
        .isoformat()
    )


def _programmes(
    records: list[dict],
    *,
    catalogue_year: int,
    guidance: str,
) -> list[DiscoveredProgramme]:
    name_counts = Counter(record["name"] for record in records)
    evidence_hash = hashlib.sha256(guidance.encode("utf-8")).hexdigest()
    programmes = []
    for record in records:
        code = record["code"]
        name = record["name"]
        mode = record["mode"]
        if name_counts[name] > 1 and mode.lower() != "in person":
            name = f"{name} ({mode})"
        programme_id = f"anu-{code.lower()}"
        if code == "7706XMCOMP":
            programme_id = EXISTING_COMPUTING_ID
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=name,
                degree_type="Master",
                faculty="Australian National University",
                department=f"{mode} delivery",
                source_url=(
                    "https://programsandcourses.anu.edu.au/"
                    f"{catalogue_year}/program/{code.lower()}"
                ),
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=guidance,
                parse_status="no-deadline",
                retrieval_method="official-api-and-page",
                evidence_quality="official-policy-guidance",
                evidence_document_hash=evidence_hash,
            )
        )
    return sorted(programmes, key=lambda item: item.id)


def _normalise(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
