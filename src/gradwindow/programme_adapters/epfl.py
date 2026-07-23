from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "cole-polytechnique-f-d-rale-de-lausanne"
CATALOG_URL = "https://www.epfl.ch/education/master/programs/"
ADMISSIONS_URL = (
    "https://www.epfl.ch/education/admission/admission-2/"
    "master-admission-criteria-application/"
)
ONLINE_APPLICATION_URL = f"{ADMISSIONS_URL}online-application/"
EXISTING_COMPUTER_SCIENCE_ID = "epfl-computer-science-msc"

_FIRST_ROUND_RE = re.compile(
    r"mid-November\s+to\s+the\s+15(?:th)?\s+of\s+December",
    flags=re.IGNORECASE,
)
_SECOND_ROUND_RE = re.compile(
    r"(?:from\s+)?the\s+16(?:th)?\s+of\s+December\s+to\s+the\s+31(?:st)?\s+of\s+March",
    flags=re.IGNORECASE,
)
_SEPTEMBER_INTAKE_RE = re.compile(
    r"studies\s+begin\s+in\s+early\s+September",
    flags=re.IGNORECASE,
)


class EPFLAdapter(BaseProgrammeAdapter):
    """Discover EPFL master's programmes and validate its shared policy."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = ONLINE_APPLICATION_URL
    intake = "September intake; cycle year not published"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 29) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        return self.parse_pages(
            catalog_html=fetcher(CATALOG_URL),
            admissions_html=fetcher(ADMISSIONS_URL),
        )

    def parse_pages(
        self,
        *,
        catalog_html: str,
        admissions_html: str,
    ) -> DiscoveredCatalog:
        _validate_admissions_policy(admissions_html)
        programmes = [_programme(record) for record in _catalogue_records(catalog_html)]
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "EPFL's official directory only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen_urls = set()
    for heading in soup.find_all("h4"):
        faculty = _normalise(heading.get_text(" ", strip=True))
        container = heading.find_next_sibling("div")
        if not faculty or container is None:
            continue
        for link in container.select('a.card[href*="/education/master/programs/"]'):
            title = link.select_one(".card-title")
            source_url = str(link.get("href", ""))
            if title is None or not _is_programme_url(source_url):
                continue
            if source_url in seen_urls:
                continue
            records.append(
                {
                    "name": _normalise(title.get_text(" ", strip=True)),
                    "faculty": faculty,
                    "sourceUrl": source_url,
                }
            )
            seen_urls.add(source_url)
    if not records:
        raise ValueError("EPFL master directory did not contain programme cards")
    return records


def _validate_admissions_policy(html: str) -> None:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    if (
        _FIRST_ROUND_RE.search(text) is None
        or _SECOND_ROUND_RE.search(text) is None
        or _SEPTEMBER_INTAKE_RE.search(text) is None
    ):
        raise ValueError(
            "EPFL admissions page did not contain its current yearless application "
            "rounds and September intake policy"
        )


def _programme(record: dict[str, str]) -> DiscoveredProgramme:
    source_url = record["sourceUrl"]
    slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
    programme_id = f"epfl-{slug}-master"
    if slug == "computer-science":
        programme_id = EXISTING_COMPUTER_SCIENCE_ID
    return DiscoveredProgramme(
        id=programme_id,
        name=f"MSc in {record['name']}",
        degree_type="MSc",
        faculty=record["faculty"],
        department="",
        source_url=source_url,
        application_url=ONLINE_APPLICATION_URL,
        windows=[],
        deadline_text=(
            "EPFL's official shared master's admission policy states that the "
            "first application period runs from mid-November to 15 December and "
            "the second from 16 December to 31 March, for studies beginning the "
            "following September. The page does not publish the cycle year, so "
            "these recurring dates remain monitoring evidence and no dates are "
            "inferred."
        ),
        parse_status="no-deadline",
        retrieval_method="official-master-directory-and-admissions-policy",
        evidence_quality="official-full-text",
    )


def _is_programme_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.hostname == "www.epfl.ch" and parsed.path.startswith(
        "/education/master/programs/"
    )


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u200b", "")).strip()
