from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

CATALOG_URL = "https://gsas.harvard.edu/programs"
APPLICATION_URL = "https://gsas.harvard.edu/apply"
UNIVERSITY_ID = "harvard-university"

MASTER_DEGREE_RE = re.compile(
    r"Master of (?P<label>Arts|Engineering|Science)\s+\((?P<code>AM|ME|SM)\)"
)
PAGE_RE = re.compile(r"[?&]page=(\d+)")


class HarvardAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027"
    application_opens_at_basis = "missing"

    def __init__(self, minimum_expected_programmes: int = 10) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_html = fetcher(self.catalog_url)
        soup = BeautifulSoup(first_html, "html.parser")
        last_page = _last_page_number(soup)
        html_pages = [first_html]
        html_pages.extend(
            fetcher(f"{self.catalog_url}?page={page}")
            for page in range(1, last_page + 1)
        )
        programmes = [
            programme
            for html in html_pages
            for programme in self._parse_programmes(html)
        ]
        return self._catalog_from_programmes(programmes)

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        return self._catalog_from_programmes(self._parse_programmes(html))

    def _parse_programmes(self, html: str) -> list[DiscoveredProgramme]:
        soup = BeautifulSoup(html, "html.parser")
        return [
            programme
            for row in soup.select(".views-row")
            for programme in self._parse_row(row)
        ]

    def _catalog_from_programmes(
        self,
        programmes: list[DiscoveredProgramme],
    ) -> DiscoveredCatalog:
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Harvard GSAS catalog only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _parse_row(self, row) -> list[DiscoveredProgramme]:
        title_link = row.select_one(".program-title a[href]")
        if title_link is None:
            return []
        title = _normalise_text(title_link.get_text(" ", strip=True))
        if not title:
            return []
        source_url = urljoin(self.catalog_url, title_link["href"])
        faculty = _area_of_study(row)
        programmes = []
        for degree in row.select(".paragraph--type--degree"):
            degree_type = _degree_type(degree)
            if degree_type is None:
                continue
            deadline = _deadline(degree)
            windows = (
                [
                    DiscoveredWindow(
                        round="Main deadline",
                        closes_at=deadline,
                        intake=self.intake,
                    )
                ]
                if deadline
                else []
            )
            programmes.append(
                DiscoveredProgramme(
                    id=_programme_id(title, degree_type),
                    name=f"{degree_type} {title}",
                    degree_type=degree_type,
                    faculty=faculty,
                    department=title,
                    source_url=source_url,
                    application_url=self.application_url,
                    windows=windows,
                    deadline_text=_deadline_text(title, degree_type, deadline),
                    parse_status="incomplete" if deadline else "no-deadline",
                )
            )
        return programmes


def _degree_type(degree) -> str | None:
    degree_node = degree.select_one(".field--paragraph-field-degree-type")
    text = _normalise_text(
        degree_node.get_text(" ", strip=True) if degree_node is not None else ""
    )
    match = MASTER_DEGREE_RE.search(text)
    return match.group("code") if match else None


def _deadline(degree) -> str | None:
    time_node = degree.find("time")
    if time_node is not None:
        value = time_node.get("datetime", "")
        if value:
            return (
                datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
            )
        text = _normalise_text(time_node.get_text(" ", strip=True))
        return _parse_harvard_date(text)
    return None


def _parse_harvard_date(value: str) -> str | None:
    date_text = _normalise_text(value).split("|")[0].strip()
    try:
        return datetime.strptime(date_text, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _deadline_text(title: str, degree_type: str, deadline: str | None) -> str:
    if deadline is None:
        return (
            f"{title} {degree_type} appears in the official Harvard Griffin GSAS "
            "program list, but no application-deadline date was published for "
            "that degree row."
        )
    return (
        f"Harvard Griffin GSAS lists {title} {degree_type} with a main "
        f"application deadline of {deadline}. Applications for degree programs "
        "are available in September, but no exact opening date is published."
    )


def _area_of_study(row) -> str:
    label = row.find(
        string=lambda value: _normalise_text(value) == "Area of Study Within"
    )
    if label is None:
        return ""
    field = label.find_parent(class_="field")
    if field is None:
        return ""
    values = [
        _normalise_text(item.get_text(" ", strip=True))
        for item in field.select(".field__item")
    ]
    return " | ".join(value for value in values if value)


def _last_page_number(soup: BeautifulSoup) -> int:
    pages = set()
    for link in soup.select('a[href*="page="]'):
        match = PAGE_RE.search(link.get("href", ""))
        if match:
            pages.add(int(match.group(1)))
    return max(pages) if pages else 0


def _programme_id(title: str, degree_type: str) -> str:
    return f"harvard-{_slug(title)}-{_slug(degree_type)}"


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
