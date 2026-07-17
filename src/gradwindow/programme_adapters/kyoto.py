from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "kyoto-university"
CATALOG_URL = (
    "https://www.kyoto-u.ac.jp/en/education-campus/education-and-admissions/"
    "graduate-degree-programs/graduate-schools2"
)
INFORMATICS_ADMISSIONS_URL = "https://www.i.kyoto-u.ac.jp/en/admission/application/"
EXISTING_DATA_SCIENCE_ID = "kyoto-informatics-data-science-master"

_INFORMATICS_COURSES = (
    "Intelligence Science and Technology",
    "Social Informatics",
    "Advanced Mathematical Sciences",
    "Applied Mathematics and Physics",
    "Systems Science",
    "Communications and Computer Engineering",
    "Data Science",
)
_POSTAL_PERIOD_RE = re.compile(
    r"Submission of Application Materials by post\s+Date:\s+Friday,?\s+"
    r"(?P<opens>June 5),?\s*-\s*Friday,?\s+(?P<closes>June 19),?\s+2026",
    re.I,
)


class KyotoAdapter(BaseProgrammeAdapter):
    """Discover Kyoto graduate master's degrees and Informatics exact window."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    intake = "April 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 23,
        maximum_expected_programmes: int = 28,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        pdf_url = _informatics_pdf_url(fetcher(INFORMATICS_ADMISSIONS_URL))
        opens_at, closes_at = _informatics_window(fetcher(pdf_url))
        programmes = _central_programmes(fetcher(CATALOG_URL))
        programmes.extend(_informatics_programmes(pdf_url, opens_at, closes_at))
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Kyoto's official catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "Kyoto's official catalogue unexpectedly contained "
                f"{len(programmes)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError(
                "Kyoto official catalogue generated duplicate programme IDs"
            )
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _central_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")
    if not rows:
        raise ValueError("Kyoto graduate-school catalogue table was missing")
    current_school = None
    current_url = CATALOG_URL
    programmes = []
    for row in rows[1:]:
        cells = row.select("td")
        if len(cells) == 4:
            current_school = _normalise(cells[0].get_text(" ", strip=True))
            school_link = cells[0].select_one("a[href]")
            current_url = (
                urljoin(CATALOG_URL, str(school_link["href"]))
                if school_link is not None
                else CATALOG_URL
            )
            degree = _normalise(cells[1].get_text(" ", strip=True))
            course = _normalise(cells[2].get_text(" ", strip=True))
        elif len(cells) in {2, 3} and current_school is not None:
            degree = _normalise(cells[0].get_text(" ", strip=True))
            course = _normalise(cells[1].get_text(" ", strip=True))
        else:
            continue
        is_masters = "Master's" in degree
        is_professional_masters = degree == "Professional" and current_school != "Law"
        if not (is_masters or is_professional_masters):
            continue
        if current_school == "Informatics":
            continue
        name = _programme_name(current_school, course, is_professional_masters)
        programmes.append(
            DiscoveredProgramme(
                id=f"kyoto-{_slug(current_school)}-{_slug(course)}",
                name=name,
                degree_type=_degree_type(
                    current_school, course, is_professional_masters
                ),
                faculty=f"Graduate School of {current_school}",
                department=f"Graduate School of {current_school}",
                source_url=CATALOG_URL,
                application_url=current_url,
                windows=[],
                deadline_text=(
                    "Kyoto University's official graduate-school table lists this "
                    "master's or professional master's degree. The central application "
                    "guidance states that deadlines vary by Graduate School; no dates "
                    "were inferred from the catalogue."
                ),
                parse_status="no-deadline",
                retrieval_method="official-central-graduate-school-table-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _programme_name(school: str, course: str, professional: bool) -> str:
    if "Master" in course:
        return course
    if professional:
        return f"Professional Master's Program in {course}"
    return f"Master's Program in {school} ({course})"


def _degree_type(school: str, course: str, professional: bool) -> str:
    if professional and school == "Government":
        return "MPP"
    if professional and school == "Management":
        return "MBA"
    if "Master of Arts" in course:
        return "MA"
    return "Master"


def _informatics_pdf_url(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    link = next(
        (
            item
            for item in soup.select("a[href]")
            if str(item["href"]).endswith("master-2027-4-en.pdf")
        ),
        None,
    )
    if link is None:
        raise ValueError("Kyoto Informatics page lacked the April 2027 master's PDF")
    value = urljoin(INFORMATICS_ADMISSIONS_URL, str(link["href"]))
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "www.i.kyoto-u.ac.jp"
        or not parsed.path.endswith("master-2027-4-en.pdf")
    ):
        raise ValueError("Kyoto Informatics page linked an invalid admission PDF")
    return urlunsplit(("https", "www.i.kyoto-u.ac.jp", parsed.path, "", ""))


def _informatics_window(text: str) -> tuple[str, str]:
    normalised = _normalise(text)
    if not all(course in normalised for course in _INFORMATICS_COURSES):
        raise ValueError("Kyoto Informatics PDF lacked the seven master's courses")
    match = _POSTAL_PERIOD_RE.search(normalised)
    if match is None:
        raise ValueError(
            "Kyoto Informatics PDF lacked the exact postal application period"
        )
    opens_at = _parse_date(f"{match.group('opens')} 2026")
    closes_at = _parse_date(f"{match.group('closes')} 2026")
    if date.fromisoformat(closes_at) <= date.fromisoformat(opens_at):
        raise ValueError(
            "Kyoto Informatics PDF published an invalid application period"
        )
    return opens_at, closes_at


def _informatics_programmes(
    pdf_url: str, opens_at: str, closes_at: str
) -> list[DiscoveredProgramme]:
    programmes = []
    for course in _INFORMATICS_COURSES:
        is_data_science = course == "Data Science"
        programmes.append(
            DiscoveredProgramme(
                id=(
                    EXISTING_DATA_SCIENCE_ID
                    if is_data_science
                    else f"kyoto-informatics-{_slug(course)}-master"
                ),
                name=f"Master's Program in Informatics ({course} Course)",
                degree_type="Master",
                faculty="Graduate School of Informatics",
                department="Graduate School of Informatics",
                source_url=pdf_url,
                application_url=INFORMATICS_ADMISSIONS_URL,
                windows=[
                    DiscoveredWindow(
                        round="August 2026 entrance examination",
                        opens_at=opens_at,
                        closes_at=closes_at,
                        intake="April 2027",
                        applicant_categories=["all"],
                        source_url=pdf_url,
                    )
                ],
                deadline_text=(
                    "Kyoto Informatics' official April 2027 master's guidelines list "
                    f"this course and require postal applications from {opens_at} "
                    f"through {closes_at}."
                ),
                parse_status="parsed",
                retrieval_method="official-informatics-admission-pdf",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _parse_date(value: str) -> str:
    return datetime.strptime(value, "%B %d %Y").date().isoformat()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").replace("’", "'").split())
