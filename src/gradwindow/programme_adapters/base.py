from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DiscoveredWindow:
    round: str
    closes_at: str
    applicant_categories: list[str] = field(default_factory=lambda: ["all"])
    opens_at: str | None = None
    intake: str | None = None


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


@dataclass(slots=True)
class DiscoveredCatalog:
    application_opens_at: str | None
    programmes: list[DiscoveredProgramme]
