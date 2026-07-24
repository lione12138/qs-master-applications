from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme, Fetcher

UNIVERSITY_ID = "the-university-of-auckland"
CATALOG_URL = (
    "https://www.auckland.ac.nz/en/study/study-options/find-a-study-option.html"
)
APPLICATION_URL = (
    "https://www.auckland.ac.nz/en/study/applications-and-admissions/apply-now.html"
)
DEADLINES_URL = (
    "https://www.auckland.ac.nz/en/study/applications-and-admissions/how-to-apply/"
    "postgraduate-application-closing-dates.html"
)
EXISTING_DATA_SCIENCE_ID = "auckland-data-science-master"


class AucklandAdapter(BaseProgrammeAdapter):
    """Discover Auckland master's degrees from the official study-option list."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 90) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(self, fetcher: Fetcher) -> DiscoveredCatalog:
        catalogue_html = fetcher(CATALOG_URL)
        deadline_html = fetcher(DEADLINES_URL)
        deadline_text = _normalise(
            BeautifulSoup(deadline_html, "html.parser").get_text(" ", strip=True)
        ).lower()
        if "application closing dates" not in deadline_text:
            raise ValueError(
                "Auckland's official deadline policy could not be verified"
            )
        return self.parse_catalog(catalogue_html)

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        programmes = []
        for item in soup.select("li.page-listing__item"):
            if item.select_one('[data-programme-type="Masters degree"]') is None:
                continue
            name_node = item.select_one("[data-programme-name]")
            link = item.select_one("a[href]")
            faculty_node = item.select_one("[data-programme-faculty]")
            if name_node is None or link is None or faculty_node is None:
                continue
            name = _normalise(name_node.get("data-programme-name"))
            faculty = _normalise(faculty_node.get("data-programme-faculty"))
            source_url = urljoin(CATALOG_URL, str(link.get("href", "")))
            programme_id = f"auckland-{_slugify(name)}"
            if name == "Master of Data Science":
                programme_id = EXISTING_DATA_SCIENCE_ID
            programmes.append(
                DiscoveredProgramme(
                    id=programme_id,
                    name=name,
                    degree_type=_degree_type(name),
                    faculty=faculty,
                    department=faculty,
                    source_url=source_url,
                    application_url=APPLICATION_URL,
                    windows=[],
                    deadline_text=(
                        "Auckland publishes official programme-specific and general "
                        f"postgraduate closing dates at {DEADLINES_URL}, but does not "
                        "publish an exact application opening date for this programme. "
                        "No opening date is inferred."
                    ),
                    parse_status="no-deadline",
                    retrieval_method="official-study-option-directory",
                    evidence_quality="official-full-text",
                )
            )
        programmes.sort(key=lambda programme: programme.name)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Auckland's official study-option directory only contained "
                f"{len(programmes)} master's degrees; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _degree_type(name: str) -> str:
    match = re.search(r"\(([^()]+)\)\s*$", name)
    return match.group(1) if match else "Master"


def _slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
