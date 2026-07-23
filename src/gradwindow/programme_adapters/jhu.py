from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "johns-hopkins-university"
CATALOG_URL = "https://e-catalogue.jhu.edu/programs/"
EP_APPLICATION_URL = "https://ep.jhu.edu/admissions-aid/admissions/how-to-apply/"
EXISTING_EP_CS_ID = "jhu-engineering-professionals-computer-science-ms"

_CATALOGUE_ID_RE = re.compile(r"^isotope-item(?P<id>\d+)$")
_DEGREE_PATTERNS = (
    (re.compile(r"\bMaster of Science in Engineering\b", re.IGNORECASE), "MSE"),
    (re.compile(r"\bMaster of Health Science\b", re.IGNORECASE), "MHS"),
    (re.compile(r"\bMaster of Public Health\b", re.IGNORECASE), "MPH"),
    (re.compile(r"\bMaster of Health Administration\b", re.IGNORECASE), "MHA"),
    (re.compile(r"\bMaster of Business Administration\b", re.IGNORECASE), "MBA"),
    (re.compile(r"\bMaster of Fine Arts\b", re.IGNORECASE), "MFA"),
    (re.compile(r"\bMaster of Music\b", re.IGNORECASE), "MM"),
    (re.compile(r"\bMaster of Education\b", re.IGNORECASE), "MEd"),
    (re.compile(r"\bMaster of Laws\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\bMaster of Arts\b", re.IGNORECASE), "MA"),
    (re.compile(r"\bMaster of Science\b", re.IGNORECASE), "MS"),
    (re.compile(r"(?:^|[,/ ])MSE(?:$|[,/ ])", re.IGNORECASE), "MSE"),
    (re.compile(r"(?:^|[,/ ])MHS(?:$|[,/ ])", re.IGNORECASE), "MHS"),
    (re.compile(r"(?:^|[,/ ])MPH(?:$|[,/ ])", re.IGNORECASE), "MPH"),
    (re.compile(r"(?:^|[,/ ])MHA(?:$|[,/ ])", re.IGNORECASE), "MHA"),
    (re.compile(r"(?:^|[,/ ])MBA(?:$|[,/ ])", re.IGNORECASE), "MBA"),
    (re.compile(r"(?:^|[,/ ])MFA(?:$|[,/ ])", re.IGNORECASE), "MFA"),
    (re.compile(r"(?:^|[,/ ])MS(?:$|[,/ ])", re.IGNORECASE), "MS"),
    (re.compile(r"(?:^|[,/ ])MA(?:$|[,/ ])", re.IGNORECASE), "MA"),
)


class JHUAdapter(BaseProgrammeAdapter):
    """Discover master's programmes from JHU's university-wide catalogue."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = CATALOG_URL
    intake = "Varies by programme and academic division"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 240) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        programmes = [_programme(record) for record in _catalogue_records(html)]
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "JHU's official catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen_urls = set()
    for item in soup.select("li.item.filter_4"):
        link = item.select_one("a[href]")
        title_node = item.select_one(".title")
        catalogue_match = _CATALOGUE_ID_RE.fullmatch(str(item.get("id", "")))
        if link is None or title_node is None or catalogue_match is None:
            continue
        source_url = urljoin(CATALOG_URL, str(link.get("href", "")))
        if urlparse(source_url).netloc != "e-catalogue.jhu.edu":
            continue
        if source_url in seen_urls:
            continue
        divisions = [
            _normalise(node.get_text(" ", strip=True))
            for node in item.select(".divisions li")
            if _normalise(node.get_text(" ", strip=True))
        ]
        records.append(
            {
                "catalogueId": catalogue_match.group("id"),
                "name": _normalise(title_node.get_text(" ", strip=True)),
                "divisions": divisions,
                "sourceUrl": source_url,
            }
        )
        seen_urls.add(source_url)
    if not records:
        raise ValueError("JHU catalogue did not contain its master's programme list")
    return records


def _programme(record: dict[str, object]) -> DiscoveredProgramme:
    name = str(record["name"])
    source_url = str(record["sourceUrl"])
    catalogue_id = str(record["catalogueId"])
    slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
    programme_id = f"jhu-{catalogue_id}-{slug}"
    application_url = source_url
    if (
        slug == "computer-science-master"
        and "/engineering-professionals/" in source_url
    ):
        programme_id = EXISTING_EP_CS_ID
        application_url = EP_APPLICATION_URL
    divisions = list(record["divisions"])
    faculty = (
        " / ".join(str(value) for value in divisions) or "Johns Hopkins University"
    )
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=_degree_type(name),
        faculty=faculty,
        department="",
        source_url=source_url,
        application_url=application_url,
        windows=[],
        deadline_text=(
            "Johns Hopkins' official Academic Catalogue confirms this master's "
            "programme. Application windows are maintained by its academic "
            "divisions, and the central catalogue does not state an exact opening "
            "date and closing date for the same intake. Division admissions pages "
            "remain monitored and no dates are inferred."
        ),
        parse_status="no-deadline",
        retrieval_method="official-academic-catalogue",
        evidence_quality="official-full-text",
    )


def _degree_type(name: str) -> str:
    for pattern, degree_type in _DEGREE_PATTERNS:
        if pattern.search(name):
            return degree_type
    return "Master"


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u200b", "")).strip()
