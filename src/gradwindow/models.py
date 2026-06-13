from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Programme:
    id: str
    university_id: str
    name: str
    degree_type: str
    faculty: str = ""
    programme_group: str = ""
    application_url: str = ""
    source_url: str = ""
    inherits_window_from: str = ""


@dataclass(slots=True)
class ApplicationWindow:
    id: str
    university_id: str
    scope_type: str
    scope_id: str
    intake: str
    opens_at: str
    closes_at: str
    application_url: str
    source_url: str
    verified_at: str
    round: str = ""
    applicant_categories: list[str] = field(default_factory=list)
    evidence: str = ""
    status: str = "verified"
