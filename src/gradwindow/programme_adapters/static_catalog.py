from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

DEGREE_RE = re.compile(
    r"\b(MSc|MRes|MPhil|MLitt|LLM|MBA|MPH|MEd|MMus|MFin|MA|MS|Master)\b",
    flags=re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]+\s+20\d{2})\b")


@dataclass(frozen=True, slots=True)
class StaticCatalogConfig:
    university_id: str
    school_prefix: str
    catalog_url: str
    link_path_contains: str
    minimum_expected_programmes: int
    default_application_url: str
    default_intake: str
    default_application_opens_at: str | None = None
    application_opens_at_basis: str = "inferred-cycle-default"


class StaticCatalogAdapter:
    def __init__(
        self,
        config: StaticCatalogConfig,
        *,
        detail_workers: int = 8,
    ) -> None:
        self.config = config
        self.university_id = config.university_id
        self.catalog_url = config.catalog_url
        self.application_opens_at_basis = config.application_opens_at_basis
        self.intake = config.default_intake
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalog = self.parse_catalog(fetcher(self.catalog_url))

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return self._parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        f"Programme found in the official course catalogue, but "
                        f"the detail page could not be fetched during discovery: "
                        f"{type(exc).__name__}: {str(exc)[:180]}"
                    ),
                    parse_status="no-deadline",
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = list(executor.map(parse_one, catalog.programmes))
        return DiscoveredCatalog(
            application_opens_at=self.config.default_application_opens_at,
            programmes=programmes,
        )

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        programmes = [
            programme
            for link in soup.find_all("a", href=True)
            if self.config.link_path_contains in link["href"]
            if (programme := self._parse_link(link)) is not None
        ]
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(programmes) < self.config.minimum_expected_programmes:
            raise ValueError(
                f"{self.config.university_id} catalog only contained "
                f"{len(programmes)} programmes; expected at least "
                f"{self.config.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _parse_link(self, link) -> DiscoveredProgramme | None:
        text = _normalise_text(link.get_text(" ", strip=True))
        degree_match = DEGREE_RE.search(text)
        if not text or degree_match is None:
            return None
        degree_type = degree_match.group(1)
        title = _normalise_text(text[: degree_match.start()])
        if not title:
            title = text
        source_url = urljoin(self.catalog_url, link["href"])
        return DiscoveredProgramme(
            id=f"{self.config.school_prefix}-{_slug(title)}-{_slug(degree_type)}",
            name=f"{degree_type} {title}",
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=source_url,
            application_url=self.config.default_application_url,
            windows=[],
            deadline_text="Programme found in the official course catalogue.",
            parse_status="no-deadline",
        )

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
    ) -> DiscoveredProgramme:
        soup = BeautifulSoup(html, "html.parser")
        text = _normalise_text(soup.get_text(" ", strip=True))
        deadline = _deadline_after_application_label(text)
        if deadline is None:
            return programme
        excerpt = _deadline_excerpt(text)
        return replace(
            programme,
            windows=[
                DiscoveredWindow(
                    round="Main application deadline",
                    opens_at=None,
                    closes_at=deadline,
                    intake=self.config.default_intake,
                )
            ],
            deadline_text=excerpt,
            parse_status=(
                "parsed" if self.config.default_application_opens_at else "incomplete"
            ),
        )


def _deadline_after_application_label(text: str) -> str | None:
    lower = text.lower()
    start = lower.find("application deadline")
    if start < 0:
        return None
    matches = DATE_RE.findall(text[start : start + 500])
    if not matches:
        return None
    return datetime.strptime(matches[-1], "%d %B %Y").date().isoformat()


def _deadline_excerpt(text: str) -> str:
    lower = text.lower()
    start = lower.find("when to apply")
    if start < 0:
        start = lower.find("application deadline")
    if start < 0:
        start = 0
    return text[start : start + 1200]


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
