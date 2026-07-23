from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "the-university-of-tokyo"
CATALOG_URL = "https://www.u-tokyo.ac.jp/en/academics/graduate_schools.html"
APPLICATION_URL = (
    "https://www.u-tokyo.ac.jp/en/prospective-students/grad_admissions.html"
)
IST_ADMISSIONS_URL = "https://www.i.u-tokyo.ac.jp/edu/entra/entra_e.shtml"
IST_APPLICATION_URL = "https://admission.i.u-tokyo.ac.jp/"
IST_GUIDE_URL = "https://www.i.u-tokyo.ac.jp/edu/entra/2027_ag_m_e.pdf"

_CENTRAL_HOST = "www.u-tokyo.ac.jp"
_SCHOOL_PATH_RE = re.compile(r"^/en/academics/grad_[a-z_]+\.html$")
_AY_RE = re.compile(
    r"application periods for AY(?P<intake>20\d{2}) entrance examinations\s*"
    r"\(conducted in AY(?P<exam>20\d{2})\)",
    re.IGNORECASE,
)
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
_IST_WINDOW_RE = re.compile(
    rf"(?P<round>Summer|Winter) Examinations.*?"
    rf"Applications are accepted from (?:Monday|Tuesday|Wednesday|Thursday|Friday|"
    rf"Saturday|Sunday),?\s*(?P<start_month>{_MONTHS})\s+"
    rf"(?P<start_day>\d{{1,2}}),\s*until\s+\d{{1,2}}:\d{{2}}\s+on\s+"
    rf"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*"
    rf"(?P<end_month>{_MONTHS})\s+(?P<end_day>\d{{1,2}}),\s*"
    rf"(?P<year>20\d{{2}})\s*\(JST\)",
    re.IGNORECASE | re.DOTALL,
)
_IST_GUIDE_YEAR_RE = re.compile(
    r"AY(?P<intake>20\d{2}) Admission Guide:\s*Master['’]s Program.*?"
    r"Examinations Conducted in AY(?P<exam>20\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_IST_ROUND_DEPARTMENTS_RE = re.compile(
    r"(?P<round>Summer|Winter) Entrance Examinations will be held "
    r"(?:in each department:|in)\s*(?P<departments>.*?)\.\s*",
    re.IGNORECASE | re.DOTALL,
)
_IST_ENTRANCE_DATES_RE = re.compile(
    r"entrance dates for successful applicants for the Summer Entrance "
    r"Examinations and for the Winter Entrance Examinations are in April "
    r"(?P<summer>20\d{2}) and October (?P<winter>20\d{2}) respectively",
    re.IGNORECASE,
)

_STATIC_UNITS = {
    "/en/academics/grad_public_policy.html": ["Public Policy"],
    "/en/academics/grad_mathematical.html": ["Mathematical Sciences"],
}
_ONLY_MASTER_UNITS = {
    "/en/academics/grad_medicine.html": {
        "Department of Health Sciences and Nursing",
        "Department of International Health",
        "Department of Medical Science (Master's Degree)",
        "School of Public Health (Professional Degree Program)",
    },
    "/en/academics/grad_law_politics.html": {
        "School of Legal and Political Studies",
    },
}
_EXCLUDED_UNITS = {
    "/en/academics/grad_agriculture.html": {
        "Department of Veterinary Medical Sciences",
    },
    "/en/academics/grad_pharmaceutical.html": {
        "Department of Pharmacy (Doctoral Program)",
    },
}

Fetcher = Callable[[str], str]


class UTokyoAdapter(BaseProgrammeAdapter):
    """Discover UTokyo master's units from its official graduate-school pages."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Varies by graduate school"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_school_pages: int = 15,
        minimum_expected_programmes: int = 80,
        target_intake_year: int = 2027,
    ) -> None:
        self.minimum_expected_school_pages = minimum_expected_school_pages
        self.minimum_expected_programmes = minimum_expected_programmes
        self.target_intake_year = target_intake_year

    def parse_catalog_from_fetcher(self, fetcher: Fetcher) -> DiscoveredCatalog:
        school_links = _graduate_school_links(fetcher(CATALOG_URL))
        if len(school_links) < self.minimum_expected_school_pages:
            raise ValueError(
                "UTokyo official index only linked "
                f"{len(school_links)} graduate-school pages; expected at least "
                f"{self.minimum_expected_school_pages}"
            )
        ist_admissions_html = fetcher(IST_ADMISSIONS_URL)
        ist_windows = _ist_windows(
            ist_admissions_html,
            target_intake_year=self.target_intake_year,
        )
        ist_rounds_by_department = {}
        if ist_windows:
            guide_url = _ist_master_guide_url(
                ist_admissions_html,
                target_intake_year=self.target_intake_year,
            )
            ist_rounds_by_department = _ist_rounds_by_department(
                fetcher(guide_url),
                target_intake_year=self.target_intake_year,
            )
        programmes = []
        for school_url in school_links:
            programmes.extend(
                _programmes_from_school(
                    school_url,
                    fetcher(school_url),
                    ist_windows=ist_windows,
                    ist_rounds_by_department=ist_rounds_by_department,
                    target_intake_year=self.target_intake_year,
                )
            )
        programmes = sorted(programmes, key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "UTokyo official graduate-school pages only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError(
                "UTokyo official catalogue generated duplicate programme IDs"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _graduate_school_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for link in soup.select("a[href]"):
        url = urljoin(CATALOG_URL, str(link.get("href", "")))
        parsed = urlparse(url)
        if (
            parsed.scheme == "https"
            and parsed.hostname == _CENTRAL_HOST
            and _SCHOOL_PATH_RE.fullmatch(parsed.path)
            and url not in links
        ):
            links.append(url)
    return links


def _programmes_from_school(
    school_url: str,
    html: str,
    *,
    ist_windows: list[DiscoveredWindow],
    ist_rounds_by_department: dict[str, set[str]],
    target_intake_year: int,
) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("h1")
    faculty = _normalise(heading.get_text(" ", strip=True) if heading else "")
    if not faculty.startswith("Graduate School"):
        raise ValueError(
            f"UTokyo school page lacked a graduate-school heading: {school_url}"
        )
    path = urlparse(school_url).path
    units = _STATIC_UNITS.get(path) or _department_headings(soup)
    allowed = _ONLY_MASTER_UNITS.get(path)
    if allowed is not None:
        units = [unit for unit in units if unit in allowed]
    excluded = _EXCLUDED_UNITS.get(path, set())
    units = [unit for unit in units if unit not in excluded]
    if not units:
        raise ValueError(
            f"UTokyo school page contained no master's units: {school_url}"
        )

    is_ist = path == "/en/academics/grad_ist.html"
    programmes = []
    for unit in units:
        subject = _subject_name(unit)
        is_existing_cs = is_ist and subject == "Computer Science"
        programme_id = (
            "utokyo-computer-science-master"
            if is_existing_cs
            else f"utokyo-{_slug(faculty)}-{_slug(subject)}-master"
        )
        eligible_rounds = ist_rounds_by_department.get(subject, set())
        windows = (
            [window for window in ist_windows if window.round in eligible_rounds]
            if is_ist
            else []
        )
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=(
                    "Master's Program in Computer Science"
                    if is_existing_cs
                    else _programme_name(subject)
                ),
                degree_type="Master",
                faculty=faculty,
                department=subject,
                source_url=school_url,
                application_url=IST_APPLICATION_URL if is_ist else APPLICATION_URL,
                windows=windows,
                deadline_text=_deadline_text(
                    is_ist=is_ist,
                    has_target_windows=bool(windows),
                    target_intake_year=target_intake_year,
                ),
                parse_status="parsed" if windows else "no-deadline",
                retrieval_method=(
                    "official-central-school-catalogue-and-ist-admissions-html"
                    if is_ist
                    else "official-central-graduate-school-catalogue-html"
                ),
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _department_headings(soup: BeautifulSoup) -> list[str]:
    in_departments = False
    units = []
    for heading in soup.select("h2, h3"):
        text = _normalise(heading.get_text(" ", strip=True))
        if heading.name == "h2":
            in_departments = "Departments" in text
            continue
        if in_departments and text and not text.startswith("◆"):
            units.append(text)
    return units


def _ist_windows(html: str, *, target_intake_year: int) -> list[DiscoveredWindow]:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    ay_match = _AY_RE.search(text)
    if ay_match is None:
        raise ValueError(
            "UTokyo IST admissions page did not identify its examination cycle"
        )
    intake_year = int(ay_match.group("intake"))
    exam_year = int(ay_match.group("exam"))
    if intake_year != target_intake_year:
        return []
    windows = []
    for match in _IST_WINDOW_RE.finditer(text):
        year = int(match.group("year"))
        if year != exam_year:
            raise ValueError(
                "UTokyo IST application dates disagreed with the exam year"
            )
        windows.append(
            DiscoveredWindow(
                round=f"{match.group('round').title()} entrance examination",
                applicant_categories=["all"],
                opens_at=_month_date(
                    match.group("start_month"), match.group("start_day"), year
                ),
                closes_at=_month_date(
                    match.group("end_month"), match.group("end_day"), year
                ),
                intake=(
                    f"Spring (April) {intake_year}"
                    if match.group("round").lower() == "summer"
                    else f"Fall (October) {intake_year}"
                ),
                source_url=IST_ADMISSIONS_URL,
            )
        )
    if len(windows) != 2:
        raise ValueError(
            "UTokyo IST admissions page did not contain both exact application periods"
        )
    return windows


def _ist_master_guide_url(html: str, *, target_intake_year: int) -> str:
    soup = BeautifulSoup(html, "html.parser")
    expected_path = f"/edu/entra/{target_intake_year}_ag_m_e.pdf"
    for link in soup.select("a[href]"):
        url = urljoin(IST_ADMISSIONS_URL, str(link.get("href", "")))
        parsed = urlparse(url)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "www.i.u-tokyo.ac.jp"
            and parsed.path == expected_path
        ):
            return url
    raise ValueError(
        f"UTokyo IST admissions page did not link the AY{target_intake_year} "
        "master's guide"
    )


def _ist_rounds_by_department(
    guide_text: str,
    *,
    target_intake_year: int,
) -> dict[str, set[str]]:
    text = _normalise(
        BeautifulSoup(guide_text, "html.parser").get_text(" ", strip=True)
    )
    guide_match = _IST_GUIDE_YEAR_RE.search(text)
    entrance_match = _IST_ENTRANCE_DATES_RE.search(text)
    if guide_match is None or entrance_match is None:
        raise ValueError("UTokyo IST master's guide lacked its cycle or entrance dates")
    intake_year = int(guide_match.group("intake"))
    exam_year = int(guide_match.group("exam"))
    if intake_year != target_intake_year:
        return {}
    if exam_year != target_intake_year - 1:
        raise ValueError("UTokyo IST master's guide identified an unexpected exam year")
    if {
        int(entrance_match.group("summer")),
        int(entrance_match.group("winter")),
    } != {target_intake_year}:
        raise ValueError(
            "UTokyo IST master's guide identified unexpected entrance years"
        )

    rounds_by_department: dict[str, set[str]] = {}
    matches = list(_IST_ROUND_DEPARTMENTS_RE.finditer(text))
    if len(matches) != 2:
        raise ValueError("UTokyo IST master's guide lacked both examination scopes")
    for match in matches:
        round_name = f"{match.group('round').title()} entrance examination"
        raw_departments = re.sub(
            r"\b(?:and\s+)?the Department of\s+",
            "",
            match.group("departments"),
            flags=re.IGNORECASE,
        )
        raw_departments = re.sub(r";\s*and\s+", ";", raw_departments)
        for department in raw_departments.split(";"):
            name = _normalise(department).removeprefix("and ")
            if name:
                rounds_by_department.setdefault(name, set()).add(round_name)
    if len(rounds_by_department) < 2:
        raise ValueError("UTokyo IST master's guide contained too few departments")
    return rounds_by_department


def _month_date(month: str, day: str, year: int) -> str:
    return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date().isoformat()


def _subject_name(unit: str) -> str:
    value = re.sub(
        r"\s*\((?:Master's Degree|Master's program and Doctoral program|"
        r"Professional Degree Program)\)\s*$",
        "",
        unit,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"^(?:Department|Division|School) of\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return _normalise(value)


def _programme_name(subject: str) -> str:
    if subject == "Public Policy":
        return "Master of Public Policy"
    if subject == "Public Health":
        return "Master of Public Health"
    return f"Master's in {subject}"


def _deadline_text(
    *,
    is_ist: bool,
    has_target_windows: bool,
    target_intake_year: int,
) -> str:
    if is_ist and has_target_windows:
        return (
            f"The official IST admissions page publishes exact Summer and Winter "
            f"application periods for Academic Year {target_intake_year}."
        )
    if is_ist:
        return (
            "The official IST admissions page was checked, but it does not publish "
            f"an exact Academic Year {target_intake_year} application period."
        )
    return (
        "UTokyo admissions are decentralised by graduate school. The official "
        "central school catalogue confirms this master's unit, but does not publish "
        f"an exact Academic Year {target_intake_year} application period for it."
    )


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    text = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "programme"
