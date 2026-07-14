from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

CATALOG_URL = "https://www.imperial.ac.uk/study/courses/postgraduate-taught/"
APPLICATION_URL = "https://myimperial.powerappsportals.com/"
UNIVERSITY_ID = "imperial-college-london"

ROUND_HEADING_RE = re.compile(r"^Round\s+(?P<round>\d+)$", flags=re.IGNORECASE)
OPEN_CLOSE_RE = re.compile(
    r"Applications open on (?P<opens>(?:Monday|Tuesday|Wednesday|Thursday|Friday|"
    r"Saturday|Sunday)\s+\d{1,2}\s+[A-Za-z]+\s+20\d{2})\s+"
    r"Applications close on (?P<closes>(?:Monday|Tuesday|Wednesday|Thursday|Friday|"
    r"Saturday|Sunday)\s+\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
    flags=re.IGNORECASE,
)
COURSE_YEAR_RE = re.compile(r"/postgraduate-taught/(?P<year>20\d{2})/")


class ImperialAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL

    def __init__(
        self,
        minimum_expected_programmes: int = 150,
        detail_workers: int = 8,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers
        self.intake = "September 2026"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalog = self.parse_catalog(fetcher(self.catalog_url))
        pages = _pagination_pages(fetcher(self.catalog_url))
        seen_urls = {programme.source_url for programme in catalog.programmes}
        programmes = list(catalog.programmes)
        for page_number in pages:
            page_url = f"{self.catalog_url}?page={page_number}"
            page_catalog = self.parse_catalog(fetcher(page_url), validate=False)
            for programme in page_catalog.programmes:
                if programme.source_url not in seen_urls:
                    programmes.append(programme)
                    seen_urls.add(programme.source_url)

        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Imperial catalog only contained "
                f"{len(programmes)} postgraduate-taught programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = list(
                executor.map(
                    lambda programme: self._parse_detail(
                        programme,
                        fetcher(programme.source_url),
                    ),
                    programmes,
                )
            )
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def parse_catalog(
        self,
        html: str,
        *,
        validate: bool = True,
    ) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        programmes = [
            programme
            for card in soup.select(".course-card")
            if (programme := self._parse_card(card)) is not None
        ]
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if validate and not programmes:
            raise ValueError("Imperial postgraduate-taught course cards were not found")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _parse_card(self, card) -> DiscoveredProgramme | None:
        title_link = card.select_one(".course-card__title a[href]")
        if title_link is None:
            return None
        title = _normalise_text(title_link.get_text(" ", strip=True))
        degree_node = card.select_one(".course-tags-list__qualification")
        degree_type = (
            _normalise_text(degree_node.get_text(" ", strip=True))
            if degree_node is not None
            else ""
        )
        if not title or not degree_type:
            return None
        source_url = _canonical_url(urljoin(self.catalog_url, title_link["href"]))
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
                "Imperial's postgraduate-taught course directory identifies this "
                "course; exact application rounds are parsed from the course page "
                "when published."
            ),
            parse_status="no-deadline",
        )

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
    ) -> DiscoveredProgramme:
        soup = BeautifulSoup(html, "html.parser")
        facts = _course_facts(soup)
        department = facts.get("Delivered by", "")
        intake = facts.get("Start date") or _intake_from_url(programme.source_url)
        application_url = _apply_url(soup) or programme.application_url
        rounds_text, windows = _application_rounds(soup, intake or self.intake)
        if not windows:
            return replace(
                programme,
                faculty="",
                department=department,
                application_url=application_url,
                deadline_text=_how_to_apply_excerpt(soup) or programme.deadline_text,
            )
        return replace(
            programme,
            faculty="",
            department=department,
            application_url=application_url,
            windows=windows,
            deadline_text=rounds_text,
            parse_status="parsed",
        )


def _pagination_pages(html: str) -> list[int]:
    soup = BeautifulSoup(html, "html.parser")
    pages = set()
    for link in soup.select("nav.pagination a[href]"):
        match = re.search(r"[?&]page=(\d+)", link["href"])
        if match:
            pages.add(int(match.group(1)))
    if not pages:
        return []
    return list(range(2, max(pages) + 1))


def _course_facts(soup: BeautifulSoup) -> dict[str, str]:
    facts: dict[str, str] = {}
    for item in soup.select(".course-key-facts__items > li"):
        heading = item.find("h3")
        if heading is None:
            continue
        key = _normalise_text(heading.get_text(" ", strip=True))
        values = [
            _normalise_text(node.get_text(" ", strip=True))
            for node in item.find_all("h4")
        ]
        values = [value for value in values if value]
        if key and values:
            facts[key] = " | ".join(values)
    return facts


def _application_rounds(
    soup: BeautifulSoup,
    intake: str,
) -> tuple[str, list[DiscoveredWindow]]:
    heading = next(
        (
            node
            for node in soup.find_all(["h2", "h3"])
            if _normalise_text(node.get_text(" ", strip=True)).lower()
            == "application rounds"
        ),
        None,
    )
    if heading is None:
        return "", []

    windows: list[DiscoveredWindow] = []
    containers = []
    current = heading
    while current := current.find_next_sibling():
        if current.name in {"h2", "h3"}:
            break
        containers.append(current)
    excerpt_parts = [
        _normalise_text(container.get_text(" ", strip=True))
        for container in containers
        if _normalise_text(container.get_text(" ", strip=True))
    ]

    for container in containers:
        for current in container.find_all("h4"):
            text = _normalise_text(current.get_text(" ", strip=True))
            if not text:
                continue
            round_match = ROUND_HEADING_RE.match(text)
            if round_match is None:
                continue
            details_node = current.find_next_sibling(["p", "ul", "div"])
            details = (
                _normalise_text(details_node.get_text(" ", strip=True))
                if details_node is not None
                else ""
            )
            dates = OPEN_CLOSE_RE.search(details)
            if dates is None:
                continue
            windows.append(
                DiscoveredWindow(
                    round=f"Round {round_match.group('round')}",
                    opens_at=_parse_imperial_date(dates.group("opens")),
                    closes_at=_parse_imperial_date(dates.group("closes")),
                    intake=intake,
                )
            )

    return _normalise_text(" ".join(excerpt_parts)[:1600]), windows


def _how_to_apply_excerpt(soup: BeautifulSoup) -> str:
    heading = next(
        (
            node
            for node in soup.find_all(["h2", "h3"])
            if "how to apply" in _normalise_text(node.get_text(" ", strip=True)).lower()
        ),
        None,
    )
    if heading is None:
        return ""
    parts = []
    current = heading
    while current := current.find_next_sibling():
        if current.name in {"h2", "h3"}:
            break
        text = _normalise_text(current.get_text(" ", strip=True))
        if text:
            parts.append(text)
    return _normalise_text(" ".join(parts)[:1200])


def _apply_url(soup: BeautifulSoup) -> str | None:
    for link in soup.find_all("a", href=True):
        if _normalise_text(link.get_text(" ", strip=True)).lower() == "apply now":
            return urljoin(CATALOG_URL, link["href"])
    return None


def _parse_imperial_date(value: str) -> str:
    return datetime.strptime(_normalise_text(value), "%A %d %B %Y").date().isoformat()


def _intake_from_url(url: str) -> str | None:
    match = COURSE_YEAR_RE.search(url)
    if match is None:
        return None
    return f"September {match.group('year')}"


def _programme_id(title: str, degree_type: str) -> str:
    return f"imperial-{_slug(title)}-{_slug(degree_type)}"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
