from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "carnegie-mellon-university"
CATALOG_URL = "https://coursecatalog.web.cmu.edu/degreesoffered/graduate-degrees/"
CATALOG_FETCH_URL = "http://coursecatalog.web.cmu.edu/degreesoffered/graduate-degrees/"
APPLICATION_URL = "https://www.cmu.edu/graduate/prospective/"
EXISTING_CS_ID = "cmu-computer-science-ms"

_MASTER_RE = re.compile(r"^(?:M\.|Master)", re.IGNORECASE)


class CMUAdapter(BaseProgrammeAdapter):
    """Discover master's offerings from CMU's university course catalog."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027 or latest programme-specific intake"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 170,
        maximum_expected_programmes: int = 185,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        programmes = sorted(
            _programmes(fetcher(CATALOG_FETCH_URL)), key=lambda item: item.id
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "CMU's official graduate-degree catalog only contained "
                f"{len(programmes)} reviewable master's programmes; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "CMU's official graduate-degree catalog unexpectedly contained "
                f"{len(programmes)} reviewable master's programmes; expected at "
                f"most {self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("CMU graduate-degree catalog generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("#content") or soup.select_one("main") or soup
    programmes = []
    for department_heading in content.select("h4"):
        programme_list = department_heading.find_next_sibling("ul")
        faculty_heading = department_heading.find_previous("h2")
        if programme_list is None or faculty_heading is None:
            continue
        faculty = _normalise(faculty_heading.get_text(" ", strip=True))
        department = _normalise(department_heading.get_text(" ", strip=True))
        for item in programme_list.select(":scope > li"):
            catalog_name = _normalise(item.get_text(" ", strip=True))
            if not _MASTER_RE.match(catalog_name):
                continue
            if "5th Year Scholars Program only" in catalog_name:
                continue
            is_existing_cs = catalog_name == "M.S. in Computer Science"
            name = "MS in Computer Science" if is_existing_cs else catalog_name
            programmes.append(
                DiscoveredProgramme(
                    id=(
                        EXISTING_CS_ID
                        if is_existing_cs
                        else f"cmu-{_slug(catalog_name)}"
                    ),
                    name=name,
                    degree_type=_degree_type(catalog_name),
                    faculty=faculty,
                    department=department,
                    source_url=CATALOG_URL,
                    application_url=APPLICATION_URL,
                    windows=[],
                    deadline_text=(
                        "CMU's official graduate-degree catalog confirms this "
                        "master's offering. CMU directs graduate applicants to the "
                        "individual school or programme because admission dates are "
                        "department-specific; no exact current-cycle opening and "
                        "closing pair is inferred from yearless or school-level dates."
                    ),
                    parse_status="no-deadline",
                    retrieval_method="official-university-graduate-degree-catalog-html",
                    evidence_quality="official-full-text",
                )
            )
    return programmes


def _degree_type(name: str) -> str:
    replacements = (
        ("M.B.A./M.S.", "MBA / MS"),
        ("M.B.A/M.S.", "MBA / MS"),
        ("M.B.A/M.S", "MBA / MS"),
        ("M.F.A.", "MFA"),
        ("M.S.", "MS"),
        ("M.A.", "MA"),
        ("M. Music", "MM"),
        ("M. Design", "MDes"),
        ("M. of", "Master"),
        ("Master of", "Master"),
    )
    for prefix, degree_type in replacements:
        if name.startswith(prefix):
            return degree_type
    return "Master"


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
