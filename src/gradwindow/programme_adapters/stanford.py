from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

CATALOG_URL = (
    "https://applygrad.stanford.edu/portal/explore-programs?cmd=grad-program-list"
)
PUBLIC_CATALOG_URL = "https://gradadmissions.stanford.edu/explore-programs"
APPLICATION_URL = "https://gradadmissions.stanford.edu/apply"
UNIVERSITY_ID = "stanford-university"

MASTER_DEGREES = {"MA", "MFA", "MLA", "MPP", "MS"}
ENTRY_TERM_RE = re.compile(
    r"^(?P<term>Autumn|Fall|Winter|Spring|Summer)\s+"
    r"(?P<start_year>20\d{2})-(?P<end_year>20\d{2})$",
    flags=re.IGNORECASE,
)
DEGREE_SUFFIX_RE = re.compile(r"\s+\((?P<degree>[A-Za-z]+)\)$")


class StanfordAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Autumn 2026"

    def __init__(self, minimum_expected_programmes: int = 40) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        programmes = [
            programme
            for card in soup.select(".program")
            if (programme := self._parse_card(card)) is not None
        ]
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Stanford catalog only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _parse_card(self, card) -> DiscoveredProgramme | None:
        degree_type = _first_token(card.get("data-degree", ""))
        if degree_type not in MASTER_DEGREES:
            return None
        official_name = _normalise_text(card.get("data-name", ""))
        title = _title_without_degree(official_name, degree_type)
        if not title:
            return None
        faculty = _first_token(card.get("data-school", ""), separator=";")
        program_website = _program_website(card)
        windows = _programme_windows(card)
        return DiscoveredProgramme(
            id=_programme_id(title, degree_type),
            name=_programme_name(title, degree_type),
            degree_type=degree_type,
            faculty=faculty,
            department=title,
            source_url=CATALOG_URL,
            application_url=self.application_url,
            windows=windows,
            deadline_text=_deadline_text(official_name, windows, program_website),
            parse_status="incomplete" if windows else "no-deadline",
        )


def _programme_windows(card) -> list[DiscoveredWindow]:
    windows: list[DiscoveredWindow] = []
    for section in card.select(".section-block"):
        heading_node = section.select_one(".heading")
        table = section.find("table")
        if heading_node is None or table is None:
            continue
        heading = _clean_heading(heading_node.get_text(" ", strip=True))
        if not heading or heading.lower() == "testing requirements":
            continue
        headers = [
            _normalise_text(header.get_text(" ", strip=True)).lower()
            for header in table.select("thead th")
        ]
        if headers[:2] != ["entry term", "application deadline"]:
            continue
        for row in table.select("tbody tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) < 2:
                continue
            entry_term = _normalise_text(cells[0].get_text(" ", strip=True))
            deadline_text = _normalise_text(cells[1].get_text(" ", strip=True))
            closes_at = _parse_stanford_date(deadline_text)
            intake = _intake_from_entry_term(entry_term)
            if closes_at is None or intake is None:
                continue
            windows.append(
                DiscoveredWindow(
                    round=heading,
                    closes_at=closes_at,
                    intake=intake,
                )
            )
    return windows


def _program_website(card) -> str | None:
    for link in card.select('a[href][aria-label^="Program Website"]'):
        return urljoin(PUBLIC_CATALOG_URL, link["href"])
    return None


def _deadline_text(
    official_name: str,
    windows: list[DiscoveredWindow],
    program_website: str | None,
) -> str:
    website_note = f" Program website: {program_website}." if program_website else ""
    if not windows:
        return (
            f"{official_name} appears in Stanford's official Explore Graduate "
            "Programs portal, but no application-deadline rows were parsed."
            f"{website_note}"
        )
    parts = [
        f"{window.round}: {window.intake} application deadline {window.closes_at}"
        for window in windows
    ]
    return _normalise_text(
        f"{official_name}; official Stanford Explore Graduate Programs deadlines: "
        + "; ".join(parts)
        + f".{website_note}"
    )


def _intake_from_entry_term(entry_term: str) -> str | None:
    match = ENTRY_TERM_RE.match(_normalise_text(entry_term))
    if match is None:
        return None
    term = match.group("term").title()
    if term == "Fall":
        term = "Autumn"
    year = (
        int(match.group("start_year"))
        if term == "Autumn"
        else int(match.group("end_year"))
    )
    return f"{term} {year}"


def _parse_stanford_date(value: str) -> str | None:
    try:
        return datetime.strptime(_normalise_text(value), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _title_without_degree(official_name: str, degree_type: str) -> str:
    match = DEGREE_SUFFIX_RE.search(official_name)
    if match is not None and match.group("degree") == degree_type:
        return _normalise_text(official_name[: match.start()])
    return official_name


def _programme_name(title: str, degree_type: str) -> str:
    if title.lower().startswith("master "):
        return title
    return f"{degree_type} {title}"


def _programme_id(title: str, degree_type: str) -> str:
    return f"stanford-{_slug(title)}-{_slug(degree_type)}"


def _first_token(value: str, *, separator: str = ";") -> str:
    return _normalise_text(str(value).split(separator)[0])


def _clean_heading(value: str) -> str:
    cleaned = re.sub(r"\(\s*\?\s*\)", "", value)
    return _normalise_text(cleaned)


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
