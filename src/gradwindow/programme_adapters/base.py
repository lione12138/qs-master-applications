from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

Fetcher = Callable[[str], str]


@dataclass(slots=True)
class DiscoveredWindow:
    round: str
    closes_at: str
    applicant_categories: list[str] = field(default_factory=lambda: ["all"])
    opens_at: str | None = None
    intake: str | None = None
    source_url: str | None = None


@dataclass(slots=True)
class DiscoveredProgramme:
    id: str
    name: str
    degree_type: str
    faculty: str
    department: str
    source_url: str
    application_url: str
    windows: list[DiscoveredWindow]
    deadline_text: str
    parse_status: str
    retrieval_method: str | None = None
    evidence_quality: str | None = None
    evidence_document_hash: str | None = None


@dataclass(slots=True)
class DiscoveredCatalog:
    application_opens_at: str | None
    programmes: list[DiscoveredProgramme]


@runtime_checkable
class ProgrammeAdapter(Protocol):
    university_id: str
    catalog_url: str
    intake: str
    application_opens_at_basis: str
    replace_pending_candidates: bool

    def parse_catalog_from_fetcher(self, fetcher: Fetcher) -> DiscoveredCatalog: ...


class BaseProgrammeAdapter:
    """Compatibility defaults shared by every dedicated programme adapter."""

    intake = "Varies by programme"
    application_opens_at_basis = "official"
    replace_pending_candidates = False
    known_programme_window_scope_type = "programme"
    known_programme_window_scope_id: str | None = None

    def parse_catalog_from_fetcher(self, fetcher: Fetcher) -> DiscoveredCatalog:
        return self.parse_catalog(fetcher(self.catalog_url))

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        raise NotImplementedError
