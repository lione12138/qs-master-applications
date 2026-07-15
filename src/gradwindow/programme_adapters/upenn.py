from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-pennsylvania"
CATALOG_URL = "https://catalog.upenn.edu/programs/"
CENTRAL_APPLICATION_URL = "https://www.upenn.edu/academics/graduate"
ENGINEERING_ADMISSIONS_URL = "https://gradadm.seas.upenn.edu/masters/"
ENGINEERING_APPLICATION_URL = "https://gradadm.seas.upenn.edu/how-to-apply/"
ENGINEERING_FACULTY = "School of Engineering and Applied Science"
DESIGN_ADMISSIONS_URL = "https://www.design.upenn.edu/graduate-admissions/how-apply"
DESIGN_APPLICATION_URL = "https://apply.design.upenn.edu/apply/"
DESIGN_FACULTY = "Stuart Weitzman School of Design"
EXISTING_MASCS_ID = "penn-applied-science-computer-science-mas"

_MASTER_DEGREE_CODES = {
    "LLCM",
    "LLM",
    "MA",
    "MADS",
    "MAPP",
    "MARCH",
    "MASCS",
    "MBA",
    "MBDS",
    "MBE",
    "MBIOT",
    "MCI",
    "MCIT",
    "MCMI",
    "MCPL",
    "MCP",
    "MCS",
    "MEBD",
    "MEDS",
    "MES",
    "MFA",
    "MHCI",
    "MHQS",
    "MIPD",
    "ML",
    "MLA",
    "MOHS",
    "MPA",
    "MPH",
    "MPHIL",
    "MPHILED",
    "MPN",
    "MRA",
    "MS",
    "MSAG",
    "MSAWB",
    "MSBMI",
    "MSCE",
    "MSD",
    "MSE",
    "MSED",
    "MSGC",
    "MSHP",
    "MSME",
    "MSMP",
    "MSN",
    "MSNPL",
    "MSNS",
    "MSOB",
    "MSOD",
    "MSOPH",
    "MSQF",
    "MSRS",
    "MSSP",
    "MSTR",
    "MSW",
    "MUSA",
}
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_PATTERN = "|".join(month.title() for month in _MONTHS)
_OPEN_DATE = re.compile(
    rf"Application Opens?:\s*(?P<month>{_MONTH_PATTERN})\s+"
    r"(?P<day>\d{1,2}),\s*(?P<year>20\d{2})",
    re.I,
)
_DEADLINE = re.compile(
    rf"(?:(?P<round>Early|Regular)\s+)?(?:Application\s+)?Deadline:\s*"
    rf"(?P<month>{_MONTH_PATTERN})\s+(?P<day>\d{{1,2}}),\s*"
    r"(?P<year>20\d{2})",
    re.I,
)
_INTAKE = re.compile(r"\bFall\s+(20\d{2})\b", re.I)

_ENGINEERING_ALIASES = {
    "artificial intelligence mse": "artificial intelligence mse ai online",
    "computer science mascs": "applied science in computer science mas cs",
    "integrated product design mipd": "integrated product design m ipd mse ipd",
    "integrated product design mse": "integrated product design m ipd mse ipd",
    "technology and innovation mse": "technology innovation mse online",
}


class UpennAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = CENTRAL_APPLICATION_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 150) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalogue_records = _catalogue_records(fetcher(self.catalog_url))
        engineering = _engineering_windows(fetcher(ENGINEERING_ADMISSIONS_URL))
        design = _design_windows(fetcher(DESIGN_ADMISSIONS_URL))
        programmes = [
            _programme(record, engineering=engineering, design=design)
            for record in catalogue_records
        ]
        programmes.sort(key=lambda item: item.name)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Penn's official graduate catalogue only contained "
                f"{len(programmes)} unique master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(value: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(value, "html.parser")
    records = {}
    for link in soup.select("a[href]"):
        title_node = link.select_one(".title")
        if title_node is None:
            continue
        href = urljoin(CATALOG_URL, link.get("href", ""))
        if not urlparse(href).path.startswith("/graduate/programs/"):
            continue
        name = _normalise(title_node.get_text(" ", strip=True))
        keywords = [
            _normalise(node.get_text(" ", strip=True))
            for node in link.select(".keyword")
            if _normalise(node.get_text(" ", strip=True))
        ]
        degree_code = _degree_code(name)
        if "Master's" not in keywords and degree_code not in _MASTER_DEGREE_CODES:
            continue
        faculty = next((keyword for keyword in keywords if "School" in keyword), "")
        if not faculty:
            raise ValueError(f"Penn catalogue did not identify the school for {name}")
        records[href] = {
            "name": name,
            "degreeCode": degree_code or "Master",
            "faculty": faculty,
            "sourceUrl": href,
        }
    return list(records.values())


def _programme(
    record: dict[str, str],
    *,
    engineering: dict[str, list[DiscoveredWindow]],
    design: dict[str, list[DiscoveredWindow]],
) -> DiscoveredProgramme:
    name = record["name"]
    source_url = record["sourceUrl"]
    faculty = record["faculty"]
    programme_id = f"penn-{urlparse(source_url).path.rstrip('/').split('/')[-1]}"
    if _normalised_key(name) == "computer science mascs":
        programme_id = EXISTING_MASCS_ID
        name = "Applied Science in Computer Science, MAS-CS"

    windows = []
    if faculty == ENGINEERING_FACULTY and programme_id != EXISTING_MASCS_ID:
        lookup = _ENGINEERING_ALIASES.get(_normalised_key(record["name"]))
        windows = engineering.get(lookup or _normalised_key(record["name"]), [])
    elif faculty == DESIGN_FACULTY:
        windows = design.get(record["name"], [])
    if faculty == ENGINEERING_FACULTY:
        application_url = ENGINEERING_APPLICATION_URL
    elif faculty == DESIGN_FACULTY:
        application_url = DESIGN_APPLICATION_URL
    else:
        application_url = CENTRAL_APPLICATION_URL
    if windows:
        evidence = "; ".join(
            (
                f"{window.round}: {window.opens_at} to {window.closes_at}"
                if window.opens_at
                else f"{window.round}: closes {window.closes_at}; exact opening "
                "date not stated"
            )
            for window in windows
        )
        source_label = (
            "Penn Engineering's official master's admissions page"
            if faculty == ENGINEERING_FACULTY
            else "Penn Weitzman's official graduate admissions page"
        )
        deadline_text = f"{source_label} states: {evidence}."
    elif programme_id == EXISTING_MASCS_ID:
        deadline_text = (
            "This known Penn Engineering programme is already covered by the "
            "curated Penn Engineering group-level application window; the adapter "
            "does not create a duplicate programme-level window."
        )
    else:
        deadline_text = (
            "Penn's official graduate catalogue confirms this master's programme, "
            "but it does not publish a fully explicit application date range on "
            "the catalogue record. The school or programme admissions page remains "
            "monitored and no dates are inferred."
        )
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=record["degreeCode"],
        faculty=faculty,
        department="",
        source_url=source_url,
        application_url=application_url,
        windows=windows,
        deadline_text=deadline_text,
        parse_status=(
            "parsed"
            if windows and all(window.opens_at for window in windows)
            else "incomplete"
            if windows
            else "no-deadline"
        ),
        retrieval_method="official-catalog+page",
        evidence_quality="official-full-text",
    )


def _engineering_windows(value: str) -> dict[str, list[DiscoveredWindow]]:
    soup = BeautifulSoup(value, "html.parser")
    page_text = _normalise(soup.get_text(" ", strip=True))
    intake_match = _INTAKE.search(page_text)
    if intake_match is None:
        raise ValueError("Penn Engineering page did not identify the intake year")
    intake = f"Fall {intake_match.group(1)}"
    results = {}
    for card in soup.select("#programs .program"):
        heading = card.find(["h2", "h3", "h4"])
        if heading is None:
            continue
        text = _normalise(card.get_text(" ", strip=True))
        opening_match = _OPEN_DATE.search(text)
        if opening_match is None:
            continue
        opens_at = _date(opening_match)
        windows = []
        for deadline_match in _DEADLINE.finditer(text):
            closes_at = _date(deadline_match)
            if opens_at > closes_at:
                continue
            label = (deadline_match.group("round") or "Regular").title()
            windows.append(
                DiscoveredWindow(
                    round=f"{label} admissions",
                    intake=intake,
                    opens_at=opens_at,
                    closes_at=closes_at,
                    applicant_categories=["all"],
                    source_url=ENGINEERING_ADMISSIONS_URL,
                )
            )
        if windows:
            results[_normalised_key(heading.get_text(" ", strip=True))] = windows
    return results


_DESIGN_DEADLINE_GROUPS = {
    "Architecture, MS": "MS in Architecture",
    "Architecture, MArch": "Master of Architecture",
    "Architecture, MEBD": "Master of Architecture",
    "Architecture, MSD: Advanced Architectural Design": "Master of Architecture",
    "Architecture, MSD: Environmental Building Design": "Master of Architecture",
    "Architecture, MSD: Property Development and Design": "Master of Architecture",
    "Architecture, MSD: Robotics and Autonomous Systems": "Master of Architecture",
    "City & Regional Planning, MCP": "Master of City Planning",
    "Fine Arts, MFA": "Master of City Planning",
    "Historic Preservation, MSD": "Master of City Planning",
    "Historic Preservation, MSHP": "Master of City Planning",
    "Landscape Architecture & Regional Planning, MLA": "Master of City Planning",
    "Urban Spatial Analytics, MUSA": "Master of City Planning",
}


def _design_windows(value: str) -> dict[str, list[DiscoveredWindow]]:
    text = _normalise(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))
    intake_match = _INTAKE.search(text)
    if intake_match is None:
        raise ValueError("Penn Weitzman admissions page did not identify the intake")
    intake = f"Fall {intake_match.group(1)}"
    deadlines = {
        anchor: _design_deadline(text, anchor)
        for anchor in set(_DESIGN_DEADLINE_GROUPS.values())
    }
    return {
        name: [
            DiscoveredWindow(
                round="Main deadline",
                intake=intake,
                opens_at=None,
                closes_at=deadlines[anchor],
                applicant_categories=["all"],
                source_url=DESIGN_ADMISSIONS_URL,
            )
        ]
        for name, anchor in _DESIGN_DEADLINE_GROUPS.items()
    }


def _design_deadline(text: str, anchor: str) -> str:
    entry_pattern = re.compile(
        rf"(?P<month>{_MONTH_PATTERN})\s+(?P<day>\d{{1,2}}),\s*"
        rf"(?P<year>20\d{{2}}):(?P<body>.*?)(?=(?:{_MONTH_PATTERN})\s+"
        r"\d{1,2},\s*20\d{2}:|$)",
        re.I,
    )
    for match in entry_pattern.finditer(text):
        if anchor.lower() in match.group("body").lower():
            return _date(match)
    raise ValueError(f"Penn Weitzman page did not list the deadline for {anchor}")


def _degree_code(name: str) -> str:
    match = re.search(r",\s*([A-Za-z0-9]+)\s*(?::|$)", name)
    if match is not None:
        return match.group(1).upper()
    for code in sorted(_MASTER_DEGREE_CODES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(code)}\b", name, re.I):
            return code
    return ""


def _date(match: re.Match[str]) -> str:
    return date(
        int(match.group("year")),
        _MONTHS[match.group("month").lower()],
        int(match.group("day")),
    ).isoformat()


def _normalised_key(value: str) -> str:
    value = value.lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
