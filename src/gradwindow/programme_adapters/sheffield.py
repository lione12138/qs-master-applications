from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme, Fetcher

UNIVERSITY_ID = "the-university-of-sheffield"
CATALOG_URL = "https://sheffield.ac.uk/postgraduate/taught/courses/2026"
DEADLINES_URL = "https://sheffield.ac.uk/postgraduate/deadlines"
APPLICATION_URL = "https://sheffield.ac.uk/postgraduate/taught/apply"
_MASTER_AWARD_RE = re.compile(
    r"^(MSc(?:\(Eng\))?|MA|MArch|MMedSci|MMet|MRes|LLM|MBA|MPH|MPA|MEd|MFA|"
    r"European Public Health Master|Master)(?:\s*\|.*)?$"
)


class SheffieldAdapter(BaseProgrammeAdapter):
    """Discover Sheffield's official postgraduate taught master's catalogue."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "2026-27 entry"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 100) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(self, fetcher: Fetcher) -> DiscoveredCatalog:
        catalogue_html = fetcher(CATALOG_URL)
        deadline_html = fetcher(DEADLINES_URL)
        deadline_text = _normalise(
            BeautifulSoup(deadline_html, "html.parser").get_text(" ", strip=True)
        ).lower()
        required_phrases = ("a few courses", "different dates")
        if not all(phrase in deadline_text for phrase in required_phrases):
            raise ValueError(
                "Sheffield's official deadline exceptions could not be verified"
            )
        return self.parse_catalog(catalogue_html)

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        programmes = []
        for item in soup.select(".courselisting"):
            link = item.select_one(".listcourse a[href]")
            award_node = item.select_one(".listaward")
            if link is None or award_node is None:
                continue
            award_text = _normalise(award_node.get_text(" ", strip=True))
            match = _MASTER_AWARD_RE.fullmatch(award_text)
            if match is None:
                continue
            degree_type = match.group(1)
            title = _normalise(link.get_text(" ", strip=True))
            source_url = urljoin(CATALOG_URL, str(link.get("href", "")))
            programme_id = f"sheffield-{_slugify(title)}-{_slugify(degree_type)}"
            programmes.append(
                DiscoveredProgramme(
                    id=programme_id,
                    name=f"{title} {degree_type}",
                    degree_type=degree_type,
                    faculty="The University of Sheffield",
                    department="The University of Sheffield",
                    source_url=source_url,
                    application_url=APPLICATION_URL,
                    windows=[],
                    deadline_text=(
                        "Sheffield's official deadlines page publishes exact general "
                        "opening and closing dates, but explicitly states that some "
                        "courses use exceptions shown on their individual pages. "
                        "Until those exceptions are checked systematically, no "
                        "general date is assigned to this programme."
                    ),
                    parse_status="no-deadline",
                    retrieval_method="official-postgraduate-taught-a-z",
                    evidence_quality="official-full-text",
                )
            )
        programmes.sort(key=lambda programme: programme.name)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Sheffield's official taught catalogue only contained "
                f"{len(programmes)} master's courses; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
