from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "delft-university-of-technology"
CATALOG_URL = "https://www.tudelft.nl/en/education/programmes/masters"
DATES_URL = (
    "https://www.tudelft.nl/en/education/admission-and-application/"
    "msc-international-diploma/dates-deadlines"
)
APPLICATION_URL = (
    "https://www.tudelft.nl/en/education/admission-and-application/"
    "msc-international-diploma/application-procedure"
)
INTAKE_YEAR = 2027
INTAKE = f"September {INTAKE_YEAR}"

EARLY_NON_EU_DEADLINE_PROGRAMMES = {
    "Aerospace Engineering",
    "Applied Mathematics",
    "Architecture, Urbanism and Building Sciences",
    "Computer Science",
    "Computer & Embedded Systems Engineering",
    "Data Science and Artificial Intelligence Technology",
    "Design for Interaction",
    "Electrical Engineering",
    "Integrated Product Design",
    "Management of Technology",
    "Strategic Product Design",
}


class TUDelftAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = INTAKE

    def __init__(self, minimum_expected_programmes: int = 30) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        date_rules = _parse_date_rules(fetcher(DATES_URL), INTAKE_YEAR)
        programmes = _parse_programmes(fetcher(self.catalog_url), date_rules)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                f"TU Delft master catalogue only contained {len(programmes)} "
                f"programmes; expected at least {self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _parse_programmes(
    html: str,
    date_rules: dict[str, str],
) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes: dict[str, DiscoveredProgramme] = {}
    for link in soup.find_all("a", href=True):
        label = _normalise_text(link.get_text(" ", strip=True))
        if "English |" not in label or "MSc " not in label:
            continue
        href = urljoin(CATALOG_URL, link["href"]).split("#", 1)[0]
        if "/en/education/programmes/masters/" not in urlparse(href).path:
            continue
        name = re.sub(r"^English\s+\|\s+2 years\s+\|\s+Full-time\s+", "", label)
        title = re.sub(r"^MSc\s+", "", name)
        if not title or title == name:
            continue
        programme_id = f"tu-delft-{_slug(title)}-msc"
        programmes[programme_id] = DiscoveredProgramme(
            id=programme_id,
            name=name,
            degree_type="MSc",
            faculty="",
            department="",
            source_url=href,
            application_url=APPLICATION_URL,
            windows=_programme_windows(title, date_rules),
            deadline_text=_deadline_text(title, date_rules),
            parse_status="parsed",
        )
    return sorted(programmes.values(), key=lambda item: item.id)


def _parse_date_rules(html: str, intake_year: int) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    rows = [
        [_normalise_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        for row in soup.find_all("tr")
    ]
    rows = [row for row in rows if len(row) >= 2]
    intake_row = _find_row(rows, "Intake of applications for MSc programmes")
    early_non_eu_row = _find_row(
        rows,
        "Application deadline for Non-EU/EFTA applicants",
    )
    main_deadline_row = _find_row(rows, "Application deadline EU/EFTA applicants")
    if intake_row is None:
        raise ValueError("TU Delft dates page did not list MSc application intake")
    if early_non_eu_row is None:
        raise ValueError("TU Delft dates page did not list Non-EU/EFTA early deadline")
    if main_deadline_row is None:
        raise ValueError("TU Delft dates page did not list EU/EFTA deadline")
    opens_month, opens_day = _parse_day_month(intake_row[0])
    early_month, early_day = _parse_day_month(early_non_eu_row[0])
    main_month, main_day = _parse_day_month(main_deadline_row[0])
    return {
        "opens_at": date(intake_year - 1, opens_month, opens_day).isoformat(),
        "early_non_eu_closes_at": date(
            intake_year,
            early_month,
            early_day,
        ).isoformat(),
        "main_closes_at": date(intake_year, main_month, main_day).isoformat(),
    }


def _find_row(rows: list[list[str]], needle: str) -> list[str] | None:
    return next((row for row in rows if needle in row[1]), None)


def _parse_day_month(value: str) -> tuple[int, int]:
    match = re.search(r"\b(\d{1,2})\s+([A-Z][a-z]+)\b", value)
    if match is None:
        raise ValueError(f"Could not parse day/month from TU Delft date: {value}")
    parsed = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d %B")
    return parsed.month, parsed.day


def _programme_windows(
    title: str,
    date_rules: dict[str, str],
) -> list[DiscoveredWindow]:
    opens_at = date_rules["opens_at"]
    main_closes_at = date_rules["main_closes_at"]
    if title in EARLY_NON_EU_DEADLINE_PROGRAMMES:
        return [
            DiscoveredWindow(
                round="Non-EU/EFTA early MSc deadline",
                applicant_categories=["non-eu-efta"],
                opens_at=opens_at,
                closes_at=date_rules["early_non_eu_closes_at"],
                intake=INTAKE,
                source_url=DATES_URL,
            ),
            DiscoveredWindow(
                round="EU/EFTA MSc deadline",
                applicant_categories=["eu-efta"],
                opens_at=opens_at,
                closes_at=main_closes_at,
                intake=INTAKE,
                source_url=DATES_URL,
            ),
        ]
    return [
        DiscoveredWindow(
            round="Main MSc deadline",
            applicant_categories=["all"],
            opens_at=opens_at,
            closes_at=main_closes_at,
            intake=INTAKE,
            source_url=DATES_URL,
        )
    ]


def _deadline_text(title: str, date_rules: dict[str, str]) -> str:
    if title in EARLY_NON_EU_DEADLINE_PROGRAMMES:
        return (
            "TU Delft's official Dates & Deadlines page lists MSc applications "
            f"opening on 15 October. For {title}, it lists a 15 January "
            "Non-EU/EFTA application deadline and a 1 April EU/EFTA application "
            f"deadline. Recorded for {INTAKE}: {date_rules['opens_at']} to "
            f"{date_rules['early_non_eu_closes_at']} / {date_rules['main_closes_at']}."
        )
    return (
        "TU Delft's official Dates & Deadlines page lists MSc applications "
        "opening on 15 October and 1 April as the application deadline for "
        f"EU/EFTA applicants to all MSc programmes and Non-EU/EFTA applicants "
        f"to all other MSc programmes. Recorded for {INTAKE}: "
        f"{date_rules['opens_at']} to {date_rules['main_closes_at']}."
    )


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
