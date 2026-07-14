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

CATALOG_URL = "https://www.gla.ac.uk/postgraduate/taught/"
APPLICATION_URL = "https://www.gla.ac.uk/postgraduate/apply/"
UNIVERSITY_ID = "university-of-glasgow"

MASTER_DEGREE_RE = re.compile(
    r"\b(MSc(?:\(MedSci\))?|MRes|MLitt|MEd|LLM|MBA|MAcc|MPH|MTh|MMus|MFin)\b"
)
MONTHS = (
    r"January|February|March|April|May|June|July|August|September|"
    r"October|November|December"
)
ROUND_RE = re.compile(
    rf"Round\s+(?P<round>\d+)\s+application dates:\s+"
    rf"(?P<opens>\d{{1,2}}\s+(?:{MONTHS})\s+20\d{{2}})\s+to\s+"
    rf"(?P<closes>\d{{1,2}}\s+(?:{MONTHS})\s+20\d{{2}})",
    flags=re.IGNORECASE,
)
HOME_RE = re.compile(
    rf"Home applicants\s+(?P<closes>\d{{1,2}}\s+(?:{MONTHS})\s+20\d{{2}})",
    flags=re.IGNORECASE,
)


class GlasgowAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "September 2026"

    def __init__(
        self,
        minimum_expected_programmes: int = 180,
        detail_workers: int = 8,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalog = self.parse_catalog(fetcher(self.catalog_url))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = list(
                executor.map(
                    lambda programme: self._parse_detail(
                        programme,
                        fetcher(programme.source_url),
                    ),
                    catalog.programmes,
                )
            )
        return self._catalog_from_programmes(programmes)

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        list_node = soup.select_one("ul.programme-list")
        if list_node is None:
            raise ValueError("Glasgow taught programme list was not found")
        programmes = [
            programme
            for link in list_node.select('a[href*="/postgraduate/taught/"]')
            if (programme := self._parse_link(link)) is not None
        ]
        unique = {programme.id: programme for programme in programmes}
        programmes = sorted(unique.values(), key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Glasgow catalog only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return self._catalog_from_programmes(programmes)

    def _parse_link(self, link) -> DiscoveredProgramme | None:
        text = _normalise_text(link.get_text(" ", strip=True))
        match = re.match(r"(?P<title>.+?)\s+\[(?P<award>[^\]]+)\]$", text)
        if match is None:
            return None
        title = _normalise_text(match.group("title"))
        award = _normalise_text(match.group("award"))
        degree_type = _degree_type(award)
        if degree_type is None:
            return None
        source_url = urljoin(self.catalog_url, link["href"])
        return DiscoveredProgramme(
            id=_programme_id(title, degree_type),
            name=f"{degree_type} {title}",
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=source_url,
            application_url=self.application_url,
            windows=[],
            deadline_text=(
                "The Glasgow taught degree A-Z identifies this master's programme; "
                "exact application rounds are published on the programme page."
            ),
            parse_status="no-deadline",
        )

    def _catalog_from_programmes(
        self,
        programmes: list[DiscoveredProgramme],
    ) -> DiscoveredCatalog:
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
    ) -> DiscoveredProgramme:
        soup = BeautifulSoup(html, "html.parser")
        text = _normalise_text(soup.get_text(" ", strip=True))
        section_start = text.lower().find("application deadlines")
        if section_start >= 0:
            text = text[section_start:]
        windows: list[DiscoveredWindow] = []
        for match in ROUND_RE.finditer(text):
            windows.append(
                DiscoveredWindow(
                    round=f"International and EU round {match.group('round')}",
                    applicant_categories=["international-and-eu"],
                    opens_at=_parse_glasgow_date(match.group("opens")),
                    closes_at=_parse_glasgow_date(match.group("closes")),
                    intake=self.intake,
                )
            )
        home_match = HOME_RE.search(text)
        if home_match is not None:
            windows.append(
                DiscoveredWindow(
                    round="Home applicants",
                    applicant_categories=["domestic-students"],
                    closes_at=_parse_glasgow_date(home_match.group("closes")),
                    intake=self.intake,
                )
            )
        if not windows:
            return programme
        return replace(
            programme,
            windows=windows,
            deadline_text=_normalise_text(text[:1200]),
            parse_status="incomplete"
            if any(window.opens_at is None for window in windows)
            else "parsed",
        )


def _degree_type(award: str) -> str | None:
    match = MASTER_DEGREE_RE.search(award)
    return match.group(1) if match else None


def _parse_glasgow_date(value: str) -> str:
    return datetime.strptime(_normalise_text(value), "%d %B %Y").date().isoformat()


def _programme_id(title: str, degree_type: str) -> str:
    return f"glasgow-{_slug(title)}-{_slug(degree_type)}"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())
