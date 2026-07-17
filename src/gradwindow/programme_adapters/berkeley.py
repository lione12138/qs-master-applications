from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-california-berkeley-ucb"
CATALOG_URL = "https://grad.berkeley.edu/admissions/our-programs/"
EXISTING_EECS_MENG_ID = "berkeley-eecs-meng"
EECS_MENG_APPLICATION_URL = (
    "https://eecs.berkeley.edu/academics/graduate/industry-programs/meng/"
)

_FLYOUT_ID_RE = re.compile(r"^flyout_(?P<id>\d+)$")
_FULL_DATE_FORMAT = "%B %d, %Y"


class BerkeleyAdapter(BaseProgrammeAdapter):
    """Discover Berkeley master's programmes and official closing dates."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = "https://grad.berkeley.edu/admissions/application-process/"
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 105) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        programmes = [_programme(record) for record in _catalogue_records(html)]
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Berkeley's official directory only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen_ids = set()
    for flyout in soup.select('div.flyout[id^="flyout_"]'):
        flyout_match = _FLYOUT_ID_RE.fullmatch(str(flyout.get("id", "")))
        title_node = flyout.select_one(".flyout__header__text--title h2")
        source_link = flyout.select_one(".flyout__header__text--url a[href]")
        details_table = flyout.select_one(".flyout__body__details--table")
        if (
            flyout_match is None
            or title_node is None
            or source_link is None
            or details_table is None
        ):
            continue
        details = _detail_values(details_table)
        if "Masters / Professional" not in details.get("Degrees Awarded", ""):
            continue
        catalogue_id = flyout_match.group("id")
        source_url = str(source_link.get("href", ""))
        if catalogue_id in seen_ids or not _is_official_url(source_url):
            continue
        website_link = flyout.select_one(".flyout__body__website a[href]")
        website_url = (
            str(website_link.get("href", "")) if website_link is not None else ""
        )
        department = details.get("Departments", "")
        if not department:
            department_node = flyout.select_one(".flyout__header__text--department")
            if department_node is not None:
                department = _normalise(department_node.get_text(" ", strip=True))
        records.append(
            {
                "catalogueId": catalogue_id,
                "name": _normalise(title_node.get_text(" ", strip=True)),
                "department": department or "University of California, Berkeley",
                "deadline": details.get("Application Deadline", "Unavailable"),
                "admitTerms": details.get("Admit Terms", "Varies by programme"),
                "degreeTypes": details.get("Degree Types", "Master"),
                "sourceUrl": source_url,
                "websiteUrl": website_url
                if _is_official_url(website_url)
                else source_url,
            }
        )
        seen_ids.add(catalogue_id)
    if not records:
        raise ValueError("Berkeley directory did not contain its master's programmes")
    return records


def _detail_values(table) -> dict[str, str]:
    values = {}
    for row in table.find_all("div", recursive=False):
        cells = row.find_all("div", recursive=False)
        if len(cells) < 2:
            continue
        key = _normalise(cells[0].get_text(" ", strip=True))
        value = _normalise(cells[1].get_text(" ", strip=True))
        if key:
            values[key] = value
    return values


def _programme(record: dict[str, str]) -> DiscoveredProgramme:
    source_url = record["sourceUrl"]
    slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
    programme_id = f"berkeley-{record['catalogueId']}-{slug}"
    application_url = record["websiteUrl"]
    if slug == "electrical-engineering-computer-sciences-meng":
        programme_id = EXISTING_EECS_MENG_ID
        application_url = EECS_MENG_APPLICATION_URL
    windows = _deadline_windows(record)
    deadline = record["deadline"]
    if windows:
        deadline_text = (
            f"Berkeley's official Graduate Division directory lists {deadline} "
            f"for {record['admitTerms']} admission. The central application policy "
            "does not state an exact application opening date, so the closing date "
            "remains a review candidate and no opening date is inferred."
        )
    else:
        deadline_text = (
            "Berkeley's official Graduate Division directory lists the application "
            f"deadline as {deadline!r} for {record['admitTerms']} admission. No "
            "exact opening and closing pair is available from the directory, so the "
            "programme remains monitored and no dates are inferred."
        )
    return DiscoveredProgramme(
        id=programme_id,
        name=record["name"],
        degree_type=_degree_type(record["degreeTypes"]),
        faculty=record["department"],
        department=record["department"],
        source_url=source_url,
        application_url=application_url,
        windows=windows,
        deadline_text=deadline_text,
        parse_status="incomplete" if windows else "no-deadline",
        retrieval_method="official-graduate-program-directory",
        evidence_quality="official-full-text",
    )


def _deadline_windows(record: dict[str, str]) -> list[DiscoveredWindow]:
    try:
        closes_at = datetime.strptime(record["deadline"], _FULL_DATE_FORMAT).date()
    except ValueError:
        return []
    admit_terms = record["admitTerms"]
    intake = f"{admit_terms} admission"
    return [
        DiscoveredWindow(
            round="Application deadline",
            opens_at=None,
            closes_at=closes_at.isoformat(),
            intake=intake,
            source_url=record["sourceUrl"],
        )
    ]


def _degree_type(value: str) -> str:
    compact = value.replace(".", "").replace(",", "/")
    compact = re.sub(r"\s+", "", compact)
    compact = re.sub(r"/{2,}", "/", compact).strip("/")
    return compact or "Master"


def _is_official_url(value: str) -> bool:
    hostname = urlparse(value).hostname or ""
    return hostname == "berkeley.edu" or hostname.endswith(".berkeley.edu")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u200b", "")).strip()
