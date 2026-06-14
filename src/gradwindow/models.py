from __future__ import annotations

from datetime import date
from datetime import datetime
import hashlib
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ScopeType = Literal["institution", "programme-group", "programme"]
Confidence = Literal["low", "medium", "high"]
Term = Literal["fall", "spring", "summer", "winter", "michaelmas", "other"]
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
DiscoveryState = Literal[
    "curated",
    "discovered",
    "low-confidence",
    "not-found",
    "pending",
    "error",
]


class DataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class IntakeDetails(DataModel):
    label: str
    cycle_year: int = Field(alias="cycleYear", ge=2000, le=2200)
    academic_year_end: int | None = Field(
        default=None,
        alias="academicYearEnd",
        ge=2000,
        le=2201,
    )
    term: Term
    start_month: int | None = Field(default=None, alias="startMonth", ge=1, le=12)

    @model_validator(mode="after")
    def validate_academic_year(self) -> "IntakeDetails":
        if (
            self.academic_year_end is not None
            and self.academic_year_end != self.cycle_year + 1
        ):
            raise ValueError("academicYearEnd must be cycleYear + 1")
        return self


class University(DataModel):
    id: str = Field(pattern=SLUG_PATTERN)
    qs_rank: int = Field(alias="qsRank", ge=1, le=200)
    qs_position: int = Field(alias="qsPosition", ge=1, le=200)
    rank_display: str = Field(alias="rankDisplay")
    school: str
    school_zh: str = Field(alias="schoolZh")
    country: str
    region: str
    homepage_url: AnyHttpUrl = Field(alias="homepageUrl")
    official_domains: list[str] = Field(alias="officialDomains")
    ror_id: AnyHttpUrl = Field(alias="rorId")
    ror_match_score: float = Field(alias="rorMatchScore", ge=0, le=1)
    ror_matched: bool = Field(alias="rorMatched")
    admissions_url: AnyHttpUrl | None = Field(alias="admissionsUrl")
    admissions_discovery: DiscoveryState = Field(alias="admissionsDiscovery")
    date_policy: str = Field(alias="datePolicy")
    monitor_enabled: bool = Field(alias="monitorEnabled")
    admissions_candidate_score: int | None = Field(
        alias="admissionsCandidateScore"
    )
    admissions_candidate_title: str | None = Field(
        alias="admissionsCandidateTitle"
    )

    @field_validator("official_domains")
    @classmethod
    def validate_domains(cls, value: list[str]) -> list[str]:
        if not value or any(not domain.strip() for domain in value):
            raise ValueError("must contain official domains")
        return value


class Programme(DataModel):
    id: str = Field(pattern=SLUG_PATTERN)
    university_id: str = Field(alias="universityId", pattern=SLUG_PATTERN)
    name: str
    degree_type: str = Field(alias="degreeType")
    faculty: str = ""
    programme_group: str = Field(default="", alias="programmeGroup")
    application_url: AnyHttpUrl = Field(alias="applicationUrl")
    source_url: AnyHttpUrl = Field(alias="sourceUrl")
    inherits_window_from: str = Field(default="", alias="inheritsWindowFrom")


class ApplicationWindow(DataModel):
    id: str = Field(pattern=SLUG_PATTERN)
    university_id: str = Field(alias="universityId", pattern=SLUG_PATTERN)
    scope_type: ScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId", pattern=SLUG_PATTERN)
    intake: str
    intake_details: IntakeDetails = Field(alias="intakeDetails")
    round: str = ""
    applicant_categories: list[str] = Field(alias="applicantCategories")
    opens_at: date = Field(alias="opensAt")
    closes_at: date = Field(alias="closesAt")
    application_url: AnyHttpUrl = Field(alias="applicationUrl")
    source_url: AnyHttpUrl = Field(alias="sourceUrl")
    verified_at: date = Field(alias="verifiedAt")
    evidence: str

    @field_validator("id", "university_id", "scope_id", "intake", "evidence")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("applicant_categories")
    @classmethod
    def validate_categories(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("must contain non-empty categories")
        if len(set(value)) != len(value):
            raise ValueError("must contain unique categories")
        if "all" in value and len(value) != 1:
            raise ValueError("all cannot be combined with other categories")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "ApplicationWindow":
        if self.opens_at > self.closes_at:
            raise ValueError("opensAt is after closesAt")
        if self.intake_details.label != self.intake:
            raise ValueError("intakeDetails.label must match intake")
        return self


class Prediction(DataModel):
    id: str = Field(pattern=SLUG_PATTERN)
    based_on_record_id: str = Field(
        alias="basedOnRecordId",
        pattern=SLUG_PATTERN,
    )
    university_id: str = Field(alias="universityId", pattern=SLUG_PATTERN)
    scope_type: ScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId", pattern=SLUG_PATTERN)
    intake: str
    intake_details: IntakeDetails = Field(alias="intakeDetails")
    round: str = ""
    applicant_categories: list[str] = Field(alias="applicantCategories")
    opens_at: date = Field(alias="opensAt")
    closes_at: date = Field(alias="closesAt")
    application_url: AnyHttpUrl = Field(alias="applicationUrl")
    source_url: AnyHttpUrl = Field(alias="sourceUrl")
    source_cycle: str = Field(alias="sourceCycle")
    based_on_verified_at: date = Field(alias="basedOnVerifiedAt")
    confidence: Confidence
    confidence_reason: str = Field(alias="confidenceReason")
    evidence_cycle_count: int = Field(alias="evidenceCycleCount", ge=1)
    methodology: Literal["previous-cycle-plus-one-year"]
    disclaimer: str

    @field_validator("applicant_categories")
    @classmethod
    def validate_categories(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("must contain non-empty categories")
        if len(set(value)) != len(value):
            raise ValueError("must contain unique categories")
        return value

    @field_validator("confidence_reason", "disclaimer")
    @classmethod
    def require_explanation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_prediction(self) -> "Prediction":
        if self.opens_at > self.closes_at:
            raise ValueError("opensAt is after closesAt")
        if self.intake_details.label != self.intake:
            raise ValueError("intakeDetails.label must match intake")
        return self


class ParserSource(DataModel):
    enabled: bool
    record_id: str = Field(alias="recordId", pattern=SLUG_PATTERN)
    url: AnyHttpUrl
    open_date_regex: str | None = Field(default=None, alias="openDateRegex")
    close_date_regex: str | None = Field(default=None, alias="closeDateRegex")

    @model_validator(mode="after")
    def require_pattern(self) -> "ParserSource":
        if self.enabled and not (self.open_date_regex or self.close_date_regex):
            raise ValueError("enabled parser requires at least one date regex")
        return self


class CycleGuidance(DataModel):
    entry: str
    status: str
    opens_text: str = Field(alias="opensText")
    notes: str


class WindowPolicy(DataModel):
    university_id: str = Field(alias="universityId", pattern=SLUG_PATTERN)
    model: str
    default_scope: ScopeType = Field(alias="defaultScope")
    masters_availability: Literal["broad", "limited", "unclear"] = Field(
        alias="mastersAvailability"
    )
    notes: str
    source_url: AnyHttpUrl = Field(alias="sourceUrl")
    verified_at: date = Field(alias="verifiedAt")
    cycle_guidance: CycleGuidance | None = Field(
        default=None,
        alias="cycleGuidance",
    )


class EvidenceSnapshot(DataModel):
    record_id: str = Field(alias="recordId", pattern=SLUG_PATTERN)
    university_id: str = Field(alias="universityId", pattern=SLUG_PATTERN)
    source_url: AnyHttpUrl = Field(alias="sourceUrl")
    final_url: AnyHttpUrl = Field(alias="finalUrl")
    captured_at: datetime = Field(alias="capturedAt")
    content_hash: str = Field(alias="contentHash", pattern=r"^[a-f0-9]{64}$")
    content_type: str = Field(alias="contentType")
    bytes_read: int = Field(alias="bytesRead", ge=0)
    truncated: bool
    excerpt: str
    excerpt_hash: str = Field(alias="excerptHash", pattern=r"^[a-f0-9]{64}$")

    @field_validator("excerpt")
    @classmethod
    def require_excerpt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_excerpt_hash(self) -> "EvidenceSnapshot":
        if self.captured_at.tzinfo is None:
            raise ValueError("capturedAt must include a timezone")
        expected = hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest()
        if self.excerpt_hash != expected:
            raise ValueError("excerptHash does not match excerpt")
        return self
