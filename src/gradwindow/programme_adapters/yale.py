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

UNIVERSITY_ID = "yale-university"
CATALOG_URL = "https://gsas.yale.edu/programs-of-study"
DATES_URL = (
    "https://gsas.yale.edu/admissions/phdmasters-application-process/dates-deadlines"
)
APPLICATION_PROCESS_URL = (
    "https://gsas.yale.edu/admissions/phdmasters-application-process"
)
TERMINAL_DEGREES_URL = (
    "https://catalog.yale.edu/gsas/policies-regulations/degree-requirements/"
)
EXISTING_CS_MS_ID = "yale-computer-science-ms"

_FULL_DATE_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}$"
)
_INTAKE_RE = re.compile(r"\bFall\s+(\d{4})\s+entry\b", flags=re.IGNORECASE)
_EXACT_OPEN_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
    flags=re.IGNORECASE,
)
_POLICY_NAME_OVERRIDES = {
    "english language and literature": "english",
}
_DEADLINE_NAME_OVERRIDES = {
    "computer science": "computer science ms",
    "computational biology and biomedical informatics": (
        "computational biology and biomedical informatics ms"
    ),
    "international and development economics": (
        "international development and economics"
    ),
}


class YaleAdapter(BaseProgrammeAdapter):
    """Discover Yale GSAS terminal master's programmes and current deadlines."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_PROCESS_URL
    intake = "Fall admission"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 23) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        return self.parse_pages(
            catalog_html=fetcher(CATALOG_URL),
            terminal_degrees_html=fetcher(TERMINAL_DEGREES_URL),
            dates_html=fetcher(DATES_URL),
            application_process_html=fetcher(APPLICATION_PROCESS_URL),
        )

    def parse_pages(
        self,
        *,
        catalog_html: str,
        terminal_degrees_html: str,
        dates_html: str,
        application_process_html: str,
    ) -> DiscoveredCatalog:
        terminal_names = _terminal_programme_names(terminal_degrees_html)
        deadline_dates = _deadline_dates(dates_html)
        intake_year, opening_text, application_opens_at = _application_cycle(
            application_process_html
        )
        intake = f"Fall {intake_year}"
        _validate_deadline_cycle(deadline_dates, intake_year)

        programmes = []
        for record in _catalogue_records(catalog_html):
            if not _has_masters_degree(record["degrees"]):
                continue
            programme_key = _programme_key(record["name"])
            policy_key = _POLICY_NAME_OVERRIDES.get(programme_key, programme_key)
            if policy_key not in terminal_names:
                continue
            degree_type = _terminal_degree(record["degrees"])
            deadline_key = _DEADLINE_NAME_OVERRIDES.get(
                programme_key,
                _name_key(record["name"]),
            )
            closes_at = deadline_dates.get(deadline_key)
            if closes_at is None:
                raise ValueError(
                    "Yale's current official deadline page did not contain the "
                    f"terminal master's programme {record['name']!r}"
                )
            programmes.append(
                _programme(
                    record,
                    degree_type=degree_type,
                    closes_at=closes_at,
                    opens_at=application_opens_at,
                    opening_text=opening_text,
                    intake=intake,
                )
            )

        programmes.sort(key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Yale's official GSAS sources only contained "
                f"{len(programmes)} terminal master's programmes; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        self.intake = intake
        return DiscoveredCatalog(
            application_opens_at=application_opens_at,
            programmes=programmes,
        )


def _terminal_programme_names(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    heading = next(
        (
            node
            for node in soup.find_all(["h1", "h2", "h3", "h4"])
            if "terminal m.a./m.s. degrees"
            in _normalise(node.get_text(" ", strip=True)).lower()
        ),
        None,
    )
    paragraph = heading.find_next("p") if heading is not None else None
    if paragraph is None:
        raise ValueError("Yale terminal M.A./M.S. degree policy was not found")
    text = _normalise(paragraph.get_text(" ", strip=True))
    marker = "departments and programs:"
    start = text.lower().find(marker)
    if start < 0:
        raise ValueError(
            "Yale terminal degree policy did not contain its programme list"
        )
    programme_text = text[start + len(marker) :].split(".", 1)[0]
    programme_text = re.sub(r",\s+and\s+", ", ", programme_text)
    names = {_programme_key(name) for name in programme_text.split(",") if name.strip()}
    if not names:
        raise ValueError(
            "Yale terminal degree policy contained an empty programme list"
        )
    return names


def _catalogue_records(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for item in soup.select("li.program-listing__item"):
        link = item.select_one(".program-listing__item--info a[href]")
        degree_container = item.select_one(".program-listing__degree")
        if link is None or degree_container is None:
            continue
        name = _normalise(link.get_text(" ", strip=True))
        degrees = [
            _normalise(node.get_text(" ", strip=True))
            for node in degree_container.select("li")
        ]
        division = item.select_one(".program-listing__item--info em")
        records.append(
            {
                "name": name,
                "degrees": degrees,
                "division": (
                    _normalise(division.get_text(" ", strip=True))
                    if division is not None
                    else ""
                ),
                "source_url": urljoin(CATALOG_URL, link.get("href", "")),
            }
        )
    if not records:
        raise ValueError("Yale GSAS programme listing was not found")
    return records


def _deadline_dates(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    deadlines: dict[str, str] = {}
    for heading in soup.find_all("h2"):
        heading_text = _normalise(heading.get_text(" ", strip=True))
        if _FULL_DATE_RE.fullmatch(heading_text) is None:
            continue
        closes_at = datetime.strptime(heading_text, "%B %d, %Y").date().isoformat()
        sibling = heading.find_next_sibling()
        while sibling is not None and sibling.name != "h2":
            if sibling.name == "ul":
                for item in sibling.select("li"):
                    name = _normalise(item.get_text(" ", strip=True)).rstrip("*")
                    if name:
                        deadlines[_name_key(name)] = closes_at
                break
            sibling = sibling.find_next_sibling()
    if not deadlines:
        raise ValueError("Yale's current official application deadlines were not found")
    return deadlines


def _application_cycle(html: str) -> tuple[int, str, str | None]:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    years = [int(value) for value in _INTAKE_RE.findall(text)]
    if not years:
        raise ValueError("Yale's current Fall application cycle was not found")
    intake_year = max(years)
    sentence_match = re.search(
        rf"[^.]*application for Fall {intake_year} entry[^.]*\.",
        text,
        flags=re.IGNORECASE,
    )
    opening_text = (
        _normalise(sentence_match.group(0))
        if sentence_match is not None
        else f"Application for Fall {intake_year} entry"
    )
    exact_match = _EXACT_OPEN_RE.search(opening_text)
    application_opens_at = None
    if exact_match is not None:
        application_opens_at = (
            datetime.strptime(
                " ".join(exact_match.groups()),
                "%B %d %Y",
            )
            .date()
            .isoformat()
        )
    return intake_year, opening_text, application_opens_at


def _validate_deadline_cycle(deadlines: dict[str, str], intake_year: int) -> None:
    years = {int(value[:4]) for value in deadlines.values()}
    expected = {intake_year - 1, intake_year}
    if not years <= expected or intake_year not in years:
        raise ValueError(
            f"Yale's official deadline groups do not match Fall {intake_year} entry"
        )


def _terminal_degree(degrees: object) -> str:
    masters = [
        value.split("-", 1)[0].strip()
        for value in degrees
        if re.match(r"^(MA|MS)\s+-", value)
    ]
    if len(masters) != 1:
        raise ValueError(f"Yale terminal programme had ambiguous degrees: {degrees!r}")
    return masters[0]


def _has_masters_degree(degrees: object) -> bool:
    return any(re.match(r"^(MA|MS)\s+-", value) for value in degrees)


def _programme(
    record: dict[str, object],
    *,
    degree_type: str,
    closes_at: str,
    opens_at: str | None,
    opening_text: str,
    intake: str,
) -> DiscoveredProgramme:
    source_url = str(record["source_url"])
    name = str(record["name"])
    slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
    programme_id = f"yale-{slug}-{degree_type.lower()}"
    display_name = f"{name} ({degree_type})"
    programme_key = _programme_key(name)
    if programme_key == "computer science":
        programme_id = EXISTING_CS_MS_ID
        display_name = "MS in Computer Science"
    elif programme_key == "computational biology and biomedical informatics":
        programme_id = "yale-computational-biology-biomedical-informatics-ms"
        display_name = "Computational Biology & Biomedical Informatics (MS)"
    opening_note = f"The official process page states: {opening_text} " + (
        f"The exact opening date is {opens_at}."
        if opens_at is not None
        else "This does not provide an exact opening date, so none is inferred."
    )
    return DiscoveredProgramme(
        id=programme_id,
        name=display_name,
        degree_type=degree_type,
        faculty="Graduate School of Arts and Sciences",
        department=name,
        source_url=source_url,
        application_url=APPLICATION_PROCESS_URL,
        windows=[
            DiscoveredWindow(
                round="Main deadline",
                opens_at=opens_at,
                closes_at=closes_at,
                intake=intake,
                source_url=DATES_URL,
            )
        ],
        deadline_text=(
            f"Yale GSAS lists {name} as a terminal {degree_type} programme. "
            f"The official {intake} deadline is {closes_at}. {opening_note}"
        ),
        parse_status="parsed" if opens_at is not None else "incomplete",
        retrieval_method="official-catalog-and-deadline-policy",
        evidence_quality="official-full-text",
    )


def _programme_key(value: str) -> str:
    return _name_key(re.sub(r"\([^)]*\)", "", value))


def _name_key(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .replace("&", " and ")
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_value)).strip()


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()
