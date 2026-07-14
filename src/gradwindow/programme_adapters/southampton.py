from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-southampton"
CATALOG_URL = "https://www.southampton.ac.uk/courses/postgraduate-taught"
APPLICATION_URL = "https://www.southampton.ac.uk/study/postgraduate-taught/apply"
DEFAULT_INTAKE = "September 2026"

MASTER_DEGREES = {"MA", "MBA", "LLM", "MMus", "MPA", "MPH", "MRes", "MSc"}
DATE_TEXT = (
    r"\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+20\d{2}"
)
INTAKE_RE = re.compile(
    r"(?:Next course starts|starting)\s+"
    r"(?P<intake>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?P<year>20\d{2})",
    re.I,
)


class SouthamptonAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"
    replace_pending_candidates = True
    intake = DEFAULT_INTAKE

    def __init__(
        self,
        minimum_expected_programmes: int = 190,
        detail_workers: int = 10,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        programmes = _catalogue_programmes(fetcher(CATALOG_URL))
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "University of Southampton catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return _parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        "Official course page could not be checked during "
                        f"discovery: {type(exc).__name__}: {str(exc)[:180]}"
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, programmes))
        return DiscoveredCatalog(application_opens_at=None, programmes=detailed)


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes: dict[str, DiscoveredProgramme] = {}
    for card in soup.select('li.course-list-item[data-study-level="pg_course"]'):
        link = card.find("a", href=True)
        heading = card.select_one("h3.card-title")
        if link is None or heading is None:
            continue
        degree_node = heading.find_previous("div")
        degree_type = _normalise(degree_node.get_text(" ", strip=True))
        if degree_type not in MASTER_DEGREES:
            continue
        title = _normalise(heading.get_text(" ", strip=True))
        if not title:
            continue
        name = f"{title} ({degree_type})"
        programme_id = f"southampton-{_slug(name)}"
        programmes[programme_id] = DiscoveredProgramme(
            id=programme_id,
            name=name,
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=urljoin(CATALOG_URL, link["href"]),
            application_url=APPLICATION_URL,
            windows=[],
            deadline_text=(
                "Programme found in the official University of Southampton "
                "postgraduate taught catalogue; its course page did not publish "
                "an exact application deadline."
            ),
            parse_status="no-deadline",
            retrieval_method="official-page",
            evidence_quality="official-full-text",
        )
    return sorted(programmes.values(), key=lambda item: item.id)


def _parse_detail(
    programme: DiscoveredProgramme,
    html: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    page_text = _normalise(soup.get_text(" ", strip=True))
    intake_match = INTAKE_RE.search(page_text)
    intake = (
        f"{intake_match.group('intake').title()} {intake_match.group('year')}"
        if intake_match
        else DEFAULT_INTAKE
    )
    deadline_text = _deadline_section_text(soup)
    windows = _deadline_windows(deadline_text, intake, programme.source_url)
    heading = soup.find("h1")
    title = _normalise(heading.get_text(" ", strip=True)) if heading else ""
    if not re.search(rf"\b{re.escape(programme.degree_type)}\b", title, re.I):
        title = programme.name
    return replace(
        programme,
        id=f"southampton-{_slug(title)}",
        name=title,
        windows=windows,
        deadline_text=(
            deadline_text
            if deadline_text
            else (
                "The official course page did not publish an exact application "
                "closing date."
            )
        ),
        parse_status="incomplete" if windows else "no-deadline",
    )


def _deadline_section_text(soup: BeautifulSoup) -> str:
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if _normalise(heading.get_text(" ", strip=True)).lower() != (
            "application deadlines"
        ):
            continue
        parent = heading.parent
        return _normalise(parent.get_text(" ", strip=True))
    return ""


def _deadline_windows(
    text: str,
    intake: str,
    source_url: str,
) -> list[DiscoveredWindow]:
    windows = []
    for label_pattern, round_name, categories in (
        (r"UK (?:students|applicants)", "UK students", ["domestic-students"]),
        (
            r"International (?:students|applicants)",
            "International students",
            ["international-students"],
        ),
    ):
        match = re.search(
            rf"\b(?:{label_pattern})\b.{{0,260}}?(?P<date>{DATE_TEXT})",
            text,
            re.I,
        )
        if match is None:
            continue
        windows.append(
            DiscoveredWindow(
                round=round_name,
                closes_at=_date(match.group("date")),
                applicant_categories=categories,
                intake=intake,
                source_url=source_url,
            )
        )
    if windows:
        return windows
    match = re.search(
        rf"(?:deadline to apply|applications? (?:close|are expected to close|submitted by))"
        rf".{{0,180}}?(?P<date>{DATE_TEXT})",
        text,
        re.I,
    )
    if match is None:
        return []
    return [
        DiscoveredWindow(
            round="Main deadline",
            closes_at=_date(match.group("date")),
            intake=intake,
            source_url=source_url,
        )
    ]


def _date(value: str) -> str:
    clean = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value, flags=re.I)
    return datetime.strptime(clean, "%d %B %Y").date().isoformat()


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.decode().lower()).strip("-")


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
