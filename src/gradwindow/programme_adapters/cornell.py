from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "cornell-university"
CATALOG_URL = "https://catalog.cornell.edu/programs/"
CENTRAL_APPLICATION_URL = "https://gradschool.cornell.edu/admissions/"
CS_MENG_APPLICATION_URL = (
    "https://www.cs.cornell.edu/master-engineering-computer-science/apply"
)
EXISTING_CS_MENG_ID = "cornell-computer-science-meng"

_MASTER_DEGREE_CODES = {
    "BANA-MS",
    "CSCN-MEng",
    "EENG-MEng",
    "ISCI-MPS",
    "LLM",
    "MA",
    "MAR",
    "MBA",
    "MBA/JD",
    "MBA/MILR",
    "MBA/MS",
    "MEng",
    "MFA",
    "MFS",
    "MHA",
    "MILR",
    "MLA",
    "MLA/MRP",
    "MMH",
    "MPA",
    "MPH",
    "MPS",
    "MRP",
    "MRP/MPS",
    "MS",
    "NYBANA-MS",
    "NYCS-MEng",
    "NYEE-MEng",
    "NYOR-MEng",
    "ORIE-MEng",
}
_DEGREE_RE = re.compile(r"\((?P<degree>[^()]+)\)\s*$")


class CornellAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = CENTRAL_APPLICATION_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 100) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        records = _catalogue_records(html)
        programmes = [_programme(record) for record in records]
        programmes.sort(key=lambda item: item.name)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Cornell's official catalogue only contained "
                f"{len(programmes)} unique master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    faculty_by_url = _faculty_by_url(soup)
    records = {}
    container = soup.select_one("#programsaztextcontainer")
    if container is None:
        raise ValueError("Cornell catalogue did not contain the Programs A-Z section")
    for link in container.select('a[href*="/programs/"]'):
        name = _normalise(link.get_text(" ", strip=True))
        match = _DEGREE_RE.search(name)
        if match is None or match.group("degree") not in _MASTER_DEGREE_CODES:
            continue
        source_url = urljoin(CATALOG_URL, link.get("href", ""))
        if not urlparse(source_url).path.startswith("/programs/"):
            continue
        records[source_url] = {
            "name": name,
            "degree": match.group("degree"),
            "faculty": faculty_by_url.get(source_url, "Cornell University"),
            "sourceUrl": source_url,
        }
    return list(records.values())


def _faculty_by_url(soup: BeautifulSoup) -> dict[str, str]:
    container = soup.select_one("#programsbycollegeschooltextcontainer")
    if container is None:
        return {}
    faculties: dict[str, list[str]] = {}
    for heading in container.select("h2.toggle"):
        listing = heading.find_next_sibling("div", class_="sitemap")
        if listing is None:
            continue
        faculty = _normalise(heading.get_text(" ", strip=True))
        for link in listing.select('a[href*="/programs/"]'):
            source_url = urljoin(CATALOG_URL, link.get("href", ""))
            faculties.setdefault(source_url, []).append(faculty)
    return {
        source_url: _preferred_faculty(values)
        for source_url, values in faculties.items()
    }


def _preferred_faculty(values: list[str]) -> str:
    return next((value for value in values if value != "Graduate School"), values[0])


def _programme(record: dict[str, str]) -> DiscoveredProgramme:
    source_url = record["sourceUrl"]
    slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
    programme_id = f"cornell-{slug}"
    name = record["name"]
    degree_type = _canonical_degree(record["degree"])
    application_url = source_url
    if slug == "computer-science-cscn-meng":
        programme_id = EXISTING_CS_MENG_ID
        name = "Computer Science (MEng)"
        degree_type = "MEng"
        application_url = CS_MENG_APPLICATION_URL
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=degree_type,
        faculty=record["faculty"],
        department="",
        source_url=source_url,
        application_url=application_url,
        windows=[],
        deadline_text=(
            "Cornell's official catalogue confirms this master's programme, but "
            "the catalogue does not state an exact application opening date and "
            "year-specific closing date together. The official programme admissions "
            "page remains monitored and no dates are inferred."
        ),
        parse_status="no-deadline",
        retrieval_method="official-catalog",
        evidence_quality="official-full-text",
    )


def _canonical_degree(value: str) -> str:
    if value.endswith("-MEng"):
        return "MEng"
    if value.endswith("-MPS"):
        return "MPS"
    if value.endswith("-MS"):
        return "MS"
    if value == "MAR":
        return "MArch"
    return value


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u200b", "")).strip()
