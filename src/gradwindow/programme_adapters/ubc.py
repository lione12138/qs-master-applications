from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-british-columbia"
CATALOG_URL = "https://www.grad.ubc.ca/prospective-students/graduate-degree-programs"
APPLICATION_URL = (
    "https://www.grad.ubc.ca/prospective-students/application-admission/apply-online"
)
EXISTING_CS_ID = "ubc-computer-science-msc"

_DATE_TEXT = r"\d{1,2} [A-Z][a-z]+ 20\d{2}"
_INTAKE_RE = re.compile(r"(?P<intake>[A-Z][a-z]+ 20\d{2}) Intake")
_OPEN_RE = re.compile(rf"Application Open Date (?P<date>{_DATE_TEXT})")
_CANADIAN_RE = re.compile(
    rf"Canadian Applicants? (?:Application )?Deadline (?P<date>{_DATE_TEXT})"
)
_INTERNATIONAL_RE = re.compile(
    rf"International Applicants? (?:Application )?Deadline (?P<date>{_DATE_TEXT})"
)


class UBCAdapter(BaseProgrammeAdapter):
    """Discover UBC Vancouver master's programmes and exact application windows."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Varies by programme"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 220,
        maximum_expected_programmes: int = 250,
        minimum_intake_year: int = 2027,
        detail_workers: int = 10,
        maximum_detail_failures: int = 5,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.minimum_intake_year = minimum_intake_year
        self.detail_workers = detail_workers
        self.maximum_detail_failures = maximum_detail_failures

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        programmes = []
        for page in range(10):
            page_programmes = _catalogue_programmes(fetcher(_catalogue_page_url(page)))
            if not page_programmes:
                break
            programmes.extend(page_programmes)
        programmes = sorted(programmes, key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "UBC's official catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "UBC's official catalogue unexpectedly contained "
                f"{len(programmes)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("UBC official catalogue generated duplicate IDs")

        failures = []

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return _parse_detail(
                    programme,
                    fetcher(programme.source_url),
                    minimum_intake_year=self.minimum_intake_year,
                )
            except Exception as exc:
                failures.append((programme.id, type(exc).__name__, str(exc)[:180]))
                return replace(
                    programme,
                    deadline_text=(
                        "Official UBC programme page could not be checked during "
                        f"discovery: {type(exc).__name__}: {str(exc)[:180]}"
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, programmes))
        if len(failures) > self.maximum_detail_failures:
            sample = "; ".join(": ".join(item) for item in failures[:3])
            raise ValueError(
                f"UBC detail discovery failed for {len(failures)} programmes: {sample}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=detailed)


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for row in soup.select("table.views-table tbody tr"):
        cells = [
            _normalise(cell.get_text(" ", strip=True)) for cell in row.select("td")
        ]
        link = row.select_one("td:nth-of-type(2) a[href]")
        if len(cells) < 3 or link is None:
            continue
        specialization, name, faculty = cells[:3]
        source_url = _canonical_url(urljoin(CATALOG_URL, str(link["href"])))
        programme_id = (
            EXISTING_CS_ID
            if name == "Master of Science in Computer Science (MSc)"
            else f"ubc-{_slug(name)}"
        )
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=name,
                degree_type=_degree_type(name),
                faculty=faculty,
                department=specialization,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    "Programme found in UBC's official graduate degree directory; "
                    "the programme deadline section is pending inspection."
                ),
                parse_status="no-deadline",
                retrieval_method="official-graduate-directory-and-programme-page-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _parse_detail(
    programme: DiscoveredProgramme,
    html: str,
    *,
    minimum_intake_year: int,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    deadline_block = soup.select_one(".view-gps-sits-ipo")
    if deadline_block is None:
        return replace(
            programme,
            deadline_text=(
                "UBC's official programme page does not expose the central SITS "
                "deadline block. No exact opening and closing date pair is inferred."
            ),
        )
    deadline_text = _normalise(deadline_block.get_text(" ", strip=True))
    windows = _parse_windows(
        deadline_text,
        source_url=programme.source_url,
        minimum_intake_year=minimum_intake_year,
    )
    if windows:
        evidence = deadline_text
    elif "have not yet been configured" in deadline_text:
        evidence = (
            "UBC's official programme page says application open dates and deadlines "
            "for an upcoming intake have not yet been configured."
        )
    else:
        evidence = (
            "UBC's official programme page does not publish an exact application "
            f"opening and closing date pair for a {minimum_intake_year} or later intake."
        )
    return replace(
        programme,
        windows=windows,
        deadline_text=evidence,
        parse_status="parsed" if windows else "no-deadline",
    )


def _parse_windows(
    text: str,
    *,
    source_url: str,
    minimum_intake_year: int,
) -> list[DiscoveredWindow]:
    intake_matches = list(_INTAKE_RE.finditer(text))
    windows = []
    for index, intake_match in enumerate(intake_matches):
        intake = intake_match.group("intake")
        if int(intake.rsplit(" ", 1)[1]) < minimum_intake_year:
            continue
        end = (
            intake_matches[index + 1].start()
            if index + 1 < len(intake_matches)
            else len(text)
        )
        section = text[intake_match.end() : end]
        open_match = _OPEN_RE.search(section)
        canadian_match = _CANADIAN_RE.search(section)
        international_match = _INTERNATIONAL_RE.search(section)
        if not open_match or not canadian_match or not international_match:
            continue
        opens_at = _iso_date(open_match.group("date"))
        canadian_close = _iso_date(canadian_match.group("date"))
        international_close = _iso_date(international_match.group("date"))
        if canadian_close == international_close:
            windows.append(
                DiscoveredWindow(
                    round="Application deadline",
                    applicant_categories=["all"],
                    opens_at=opens_at,
                    closes_at=canadian_close,
                    intake=intake,
                    source_url=source_url,
                )
            )
            continue
        windows.extend(
            [
                DiscoveredWindow(
                    round="Canadian applicant deadline",
                    applicant_categories=["domestic-students"],
                    opens_at=opens_at,
                    closes_at=canadian_close,
                    intake=intake,
                    source_url=source_url,
                ),
                DiscoveredWindow(
                    round="International applicant deadline",
                    applicant_categories=["international-students"],
                    opens_at=opens_at,
                    closes_at=international_close,
                    intake=intake,
                    source_url=source_url,
                ),
            ]
        )
    return windows


def _catalogue_page_url(page: int) -> str:
    return f"{CATALOG_URL}?lev=Master%27s&page={page}"


def _degree_type(name: str) -> str:
    match = re.search(r"\(([^()]*)\)$", name)
    return match.group(1) if match else "Master"


def _iso_date(value: str) -> str:
    return datetime.strptime(value, "%d %B %Y").date().isoformat()


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.grad.ubc.ca"
        or "/graduate-degree-programs/" not in parsed.path
    ):
        raise ValueError(f"UBC catalogue contained a non-official URL: {value}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
