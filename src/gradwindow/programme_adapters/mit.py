from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

CATALOG_URL = "https://oge.mit.edu/graduate-admissions/programs/masters-degrees/"
UNIVERSITY_ID = "massachusetts-institute-of-technology-mit"
MONTH_DAY_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2})\b",
    flags=re.IGNORECASE,
)


class MITAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL

    def __init__(
        self,
        minimum_expected_programmes: int = 25,
        intake_year: int | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.intake_year = intake_year or now.year + (now.month >= 5)
        self.intake = f"September {self.intake_year}"
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        table = _programme_table(soup)
        programmes = [
            programme
            for row in table.select("tbody tr")
            if (programme := self._parse_row(row)) is not None
        ]
        unique = {programme.id: programme for programme in programmes}
        programmes = sorted(unique.values(), key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "MIT catalog only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=programmes,
        )

    def _parse_row(self, row) -> DiscoveredProgramme | None:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            return None
        link = cells[0].find("a", href=True)
        name = _normalise_text(cells[0].get_text(" ", strip=True))
        if not name or link is None:
            return None
        opening_text = _normalise_text(cells[1].get_text(" ", strip=True))
        deadline_text = _normalise_text(cells[2].get_text(" ", strip=True))
        opening_dates = _month_days(opening_text)
        deadline_dates = _month_days(deadline_text)
        windows: list[DiscoveredWindow] = []
        for index, deadline in enumerate(deadline_dates):
            opening = _opening_for_deadline(opening_dates, index)
            closes_at = _cycle_date(
                deadline,
                application_year=self.intake_year - 1,
                opening=opening,
            )
            opens_at = (
                _application_date(opening, self.intake_year - 1) if opening else None
            )
            windows.append(
                DiscoveredWindow(
                    round=(
                        "Main deadline"
                        if len(deadline_dates) == 1
                        else f"Round {index + 1}"
                    ),
                    opens_at=opens_at,
                    closes_at=closes_at,
                )
            )
        if not windows:
            parse_status = "no-deadline"
        elif not opening_dates:
            parse_status = "incomplete"
        else:
            parse_status = "parsed"
        return DiscoveredProgramme(
            id=_programme_id(name),
            name=name,
            degree_type=_degree_type(name),
            faculty="",
            department=name,
            source_url=self.catalog_url,
            application_url=link["href"],
            windows=windows,
            deadline_text=(
                f"Application opens: {opening_text or 'not specified'}; "
                f"deadline: {deadline_text or 'not specified'}"
            ),
            parse_status=parse_status,
        )


def _programme_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        headings = [
            _normalise_text(node.get_text(" ", strip=True)).lower()
            for node in table.select("thead th")
        ]
        if headings[:3] == [
            "program",
            "application opens",
            "application deadline",
        ]:
            return table
    raise ValueError("MIT master's programme table was not found")


def _month_days(value: str) -> list[tuple[int, int]]:
    parsed: list[tuple[int, int]] = []
    for month, day in MONTH_DAY_RE.findall(value):
        month_number = datetime.strptime(month[:3], "%b").month
        parsed.append((month_number, int(day)))
    return parsed


def _opening_for_deadline(
    openings: list[tuple[int, int]],
    index: int,
) -> tuple[int, int] | None:
    if not openings:
        return None
    if len(openings) == 1:
        return openings[0]
    return openings[min(index, len(openings) - 1)]


def _cycle_date(
    month_day: tuple[int, int],
    *,
    application_year: int,
    opening: tuple[int, int] | None,
) -> str:
    month, day = month_day
    if opening is None:
        year = application_year + (month <= 6)
    else:
        year = application_year + (month < opening[0])
    return datetime(year, month, day).date().isoformat()


def _application_date(month_day: tuple[int, int], application_year: int) -> str:
    month, day = month_day
    return datetime(application_year, month, day).date().isoformat()


def _degree_type(name: str) -> str:
    lowered = name.lower()
    if "mba" in lowered:
        return "MBA"
    if "business analytics" in lowered:
        return "MBAn"
    if "master of finance" in lowered:
        return "MFin"
    if "master of science" in lowered:
        return "SM"
    return "Master"


def _programme_id(name: str) -> str:
    clean_name = re.sub(r"^MIT(?:-|\s)+", "", name, flags=re.IGNORECASE)
    return f"mit-{_slug(clean_name)}-masters"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())
