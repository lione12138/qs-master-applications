from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from urllib.parse import urlparse

from .discovery import same_official_domain
from .io import read_json
from .paths import (
    APPLICATIONS_PATH,
    PREDICTIONS_PATH,
    PROGRAMS_PATH,
    SOURCES_PATH,
    UNIVERSITIES_PATH,
    WINDOW_POLICIES_PATH,
)
from .predictions import (
    PREDICTION_METHOD,
    canonical_intake_key,
    official_cycle_key,
    shift_date_one_year,
    shift_intake_one_year,
)

UNIVERSITY_FIELDS = {
    "id",
    "qsRank",
    "qsPosition",
    "rankDisplay",
    "school",
    "country",
    "region",
    "homepageUrl",
    "officialDomains",
    "admissionsDiscovery",
}
APPLICATION_FIELDS = {
    "id",
    "universityId",
    "scopeType",
    "scopeId",
    "intake",
    "round",
    "opensAt",
    "closesAt",
    "applicationUrl",
    "sourceUrl",
    "verifiedAt",
    "applicantCategories",
    "evidence",
}
PROGRAM_FIELDS = {
    "id",
    "universityId",
    "name",
    "degreeType",
    "applicationUrl",
    "sourceUrl",
}
PREDICTION_FIELDS = {
    "id",
    "basedOnRecordId",
    "universityId",
    "scopeType",
    "scopeId",
    "intake",
    "round",
    "applicantCategories",
    "opensAt",
    "closesAt",
    "applicationUrl",
    "sourceUrl",
    "sourceCycle",
    "basedOnVerifiedAt",
    "confidence",
    "confidenceReason",
    "evidenceCycleCount",
    "methodology",
    "disclaimer",
}
WINDOW_SCOPE_TYPES = {"institution", "programme-group", "programme"}
MASTERS_AVAILABILITY = {"broad", "limited", "unclear"}
DISCOVERY_STATES = {
    "curated",
    "discovered",
    "low-confidence",
    "not-found",
    "pending",
    "error",
}


def valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_data(
    universities_path: Path = UNIVERSITIES_PATH,
    applications_path: Path = APPLICATIONS_PATH,
    sources_path: Path = SOURCES_PATH,
    programs_path: Path = PROGRAMS_PATH,
    policies_path: Path = WINDOW_POLICIES_PATH,
    predictions_path: Path = PREDICTIONS_PATH,
) -> tuple[list[str], dict[str, int]]:
    university_payload = read_json(universities_path)
    application_payload = read_json(applications_path)
    universities = university_payload.get("universities")
    applications = application_payload.get("applications")
    sources_payload = read_json(sources_path)
    sources = sources_payload.get("sources")
    programs = read_json(programs_path).get("programs")
    policies = read_json(policies_path).get("policies")
    predictions = read_json(predictions_path).get("predictions")
    errors: list[str] = []

    if not isinstance(universities, list) or len(universities) != 200:
        errors.append("universities must contain exactly 200 institutions")
        universities = universities or []
    if not isinstance(applications, list):
        errors.append("applications must be a list")
        applications = []
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    if not isinstance(programs, list):
        errors.append("programs must be a list")
        programs = []
    if not isinstance(policies, list):
        errors.append("window policies must be a list")
        policies = []
    if not isinstance(predictions, list):
        errors.append("predictions must be a list")
        predictions = []

    university_ids: set[str] = set()
    university_domains: dict[str, list[str]] = {}
    positions: list[int] = []
    for item in universities:
        label = item.get("id", "unknown university")
        missing = UNIVERSITY_FIELDS - item.keys()
        if missing:
            errors.append(f"{label}: missing university fields {sorted(missing)}")
            continue
        if label in university_ids:
            errors.append(f"{label}: duplicate university id")
        university_ids.add(label)
        university_domains[label] = item["officialDomains"]
        positions.append(item["qsPosition"])
        if not isinstance(item["qsRank"], int) or not 1 <= item["qsRank"] <= 200:
            errors.append(f"{label}: invalid QS rank")
        if item["admissionsDiscovery"] not in DISCOVERY_STATES:
            errors.append(f"{label}: invalid admissionsDiscovery")
        if not valid_http_url(item["homepageUrl"]):
            errors.append(f"{label}: invalid official homepage")
        if item.get("admissionsUrl") and not valid_http_url(item["admissionsUrl"]):
            errors.append(f"{label}: invalid admissions URL")
        if not isinstance(item["officialDomains"], list):
            errors.append(f"{label}: officialDomains must be a list")

    if sorted(positions) != list(range(1, 201)):
        errors.append("QS positions must be unique and cover 1 through 200")

    application_ids: set[str] = set()
    program_ids: set[str] = set()
    programs_by_id: dict[str, dict] = {}
    for item in programs:
        label = item.get("id", "unknown programme")
        missing = PROGRAM_FIELDS - item.keys()
        if missing:
            errors.append(f"{label}: missing programme fields {sorted(missing)}")
            continue
        if label in program_ids:
            errors.append(f"{label}: duplicate programme id")
        program_ids.add(label)
        programs_by_id[label] = item
        if item["universityId"] not in university_ids:
            errors.append(f"{label}: unknown universityId")
        for field in ("applicationUrl", "sourceUrl"):
            if item.get(field) and not valid_http_url(item[field]):
                errors.append(f"{label}: invalid {field}")
        if (
            valid_http_url(item.get("sourceUrl"))
            and item["universityId"] in university_domains
            and not same_official_domain(
                item["sourceUrl"], university_domains[item["universityId"]]
            )
        ):
            errors.append(f"{label}: sourceUrl is outside official domains")

    application_keys: set[tuple] = set()
    for item in applications:
        label = item.get("id", "unknown application")
        missing = APPLICATION_FIELDS - item.keys()
        if missing:
            errors.append(f"{label}: missing application fields {sorted(missing)}")
            continue
        if label in application_ids:
            errors.append(f"{label}: duplicate application id")
        application_ids.add(label)
        if item["universityId"] not in university_ids:
            errors.append(f"{label}: unknown universityId")
        scope_type = item["scopeType"]
        scope_id = item["scopeId"]
        if scope_type not in WINDOW_SCOPE_TYPES:
            errors.append(f"{label}: invalid scopeType")
        if scope_type == "institution" and scope_id != item["universityId"]:
            errors.append(
                f"{label}: institution scopeId must match universityId"
            )
        if scope_type == "programme" and scope_id not in program_ids:
            errors.append(f"{label}: programme scope references an unknown programme")
        if (
            scope_type == "programme"
            and scope_id in programs_by_id
            and programs_by_id[scope_id]["universityId"] != item["universityId"]
        ):
            errors.append(f"{label}: programme scope belongs to another university")
        categories = item["applicantCategories"]
        if not isinstance(categories, list):
            errors.append(f"{label}: applicantCategories must be a list")
        elif (
            not categories
            or any(not isinstance(value, str) or not value.strip() for value in categories)
            or len(set(categories)) != len(categories)
        ):
            errors.append(
                f"{label}: applicantCategories must contain unique non-empty strings"
            )
        elif "all" in categories and len(categories) != 1:
            errors.append(f"{label}: all cannot be combined with other categories")
        if not str(item["evidence"]).strip():
            errors.append(f"{label}: evidence is required")
        try:
            opens = date.fromisoformat(item["opensAt"])
            closes = date.fromisoformat(item["closesAt"])
            date.fromisoformat(item["verifiedAt"])
            if opens > closes:
                errors.append(f"{label}: opensAt is after closesAt")
        except (TypeError, ValueError):
            errors.append(f"{label}: dates must use YYYY-MM-DD")
        for field in ("applicationUrl", "sourceUrl"):
            if not valid_http_url(item[field]):
                errors.append(f"{label}: invalid {field}")
        if (
            valid_http_url(item.get("sourceUrl"))
            and item["universityId"] in university_domains
            and not same_official_domain(
                item["sourceUrl"], university_domains[item["universityId"]]
            )
        ):
            errors.append(f"{label}: sourceUrl is outside official domains")
        application_key = official_cycle_key(item)
        if application_key in application_keys:
            errors.append(f"{label}: duplicate semantic application window")
        application_keys.add(application_key)

    applications_by_id = {
        item["id"]: item for item in applications if APPLICATION_FIELDS <= item.keys()
    }
    official_keys = {official_cycle_key(item) for item in applications}
    prediction_ids: set[str] = set()
    prediction_keys: set[tuple] = set()
    for item in predictions:
        label = item.get("id", "unknown prediction")
        missing = PREDICTION_FIELDS - item.keys()
        if missing:
            errors.append(f"{label}: missing prediction fields {sorted(missing)}")
            continue
        if label in prediction_ids:
            errors.append(f"{label}: duplicate prediction id")
        prediction_ids.add(label)
        source = applications_by_id.get(item["basedOnRecordId"])
        if source is None:
            errors.append(f"{label}: basedOnRecordId references an unknown window")
            continue
        if item["confidence"] not in {"low", "medium", "high"}:
            errors.append(f"{label}: invalid prediction confidence")
        if not isinstance(item["evidenceCycleCount"], int) or item[
            "evidenceCycleCount"
        ] < 1:
            errors.append(f"{label}: invalid evidenceCycleCount")
        if not str(item["confidenceReason"]).strip():
            errors.append(f"{label}: confidenceReason is required")
        if item["methodology"] != PREDICTION_METHOD:
            errors.append(f"{label}: invalid prediction methodology")
        if not str(item["disclaimer"]).strip():
            errors.append(f"{label}: prediction disclaimer is required")
        for field in ("applicationUrl", "sourceUrl"):
            if not valid_http_url(item[field]):
                errors.append(f"{label}: invalid {field}")
        for field in (
            "universityId",
            "scopeType",
            "scopeId",
            "round",
            "applicantCategories",
            "applicationUrl",
            "sourceUrl",
        ):
            if item[field] != source.get(field):
                errors.append(f"{label}: {field} must match its source window")
        if item["sourceCycle"] != source["intake"]:
            errors.append(f"{label}: sourceCycle must match its source intake")
        if item["intake"] != shift_intake_one_year(source["intake"]):
            errors.append(f"{label}: intake is not a one-year shift")
        if item["basedOnVerifiedAt"] != source["verifiedAt"]:
            errors.append(
                f"{label}: basedOnVerifiedAt must match its source window"
            )
        if item["opensAt"] != shift_date_one_year(source["opensAt"]):
            errors.append(f"{label}: opensAt is not a one-year shift")
        if item["closesAt"] != shift_date_one_year(source["closesAt"]):
            errors.append(f"{label}: closesAt is not a one-year shift")
        try:
            opens = date.fromisoformat(item["opensAt"])
            closes = date.fromisoformat(item["closesAt"])
            if opens > closes:
                errors.append(f"{label}: opensAt is after closesAt")
        except (TypeError, ValueError):
            errors.append(f"{label}: dates must use YYYY-MM-DD")
        prediction_key = official_cycle_key(item)
        if prediction_key in official_keys:
            errors.append(f"{label}: an official target-cycle window already exists")
        if prediction_key in prediction_keys:
            errors.append(f"{label}: duplicate predicted target window")
        prediction_keys.add(prediction_key)

    for index, source in enumerate(sources):
        label = source.get("recordId", f"source {index}")
        if not source.get("enabled"):
            continue
        if label not in application_ids:
            errors.append(f"{label}: enabled source references an unknown application")
        if not valid_http_url(source.get("url")):
            errors.append(f"{label}: invalid source URL")
        if not source.get("openDateRegex") and not source.get("closeDateRegex"):
            errors.append(f"{label}: enabled source has no date regex")
        for field in ("openDateRegex", "closeDateRegex"):
            pattern = source.get(field)
            if not pattern:
                continue
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                errors.append(f"{label}: invalid {field}: {exc}")
                continue
            if "date" not in compiled.groupindex:
                errors.append(f"{label}: {field} must contain a named date group")

    policy_ids: set[str] = set()
    for index, policy in enumerate(policies):
        label = policy.get("universityId", f"policy {index}")
        if label in policy_ids:
            errors.append(f"{label}: duplicate window policy")
        policy_ids.add(label)
        if label not in university_ids:
            errors.append(f"{label}: policy references an unknown university")
        if policy.get("defaultScope") not in WINDOW_SCOPE_TYPES:
            errors.append(f"{label}: invalid policy defaultScope")
        if policy.get("mastersAvailability", "unclear") not in MASTERS_AVAILABILITY:
            errors.append(f"{label}: invalid mastersAvailability")
        if not valid_http_url(policy.get("sourceUrl")):
            errors.append(f"{label}: invalid policy sourceUrl")
        elif label in university_domains and not same_official_domain(
            policy["sourceUrl"], university_domains[label]
        ):
            errors.append(f"{label}: policy sourceUrl is outside official domains")
        try:
            date.fromisoformat(policy["verifiedAt"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label}: invalid policy verifiedAt")

    summary = {
        "universities": len(universities),
        "admissionsCandidates": sum(
            bool(item.get("admissionsUrl")) for item in universities
        ),
        "curatedAdmissions": sum(
            item.get("admissionsDiscovery") == "curated" for item in universities
        ),
        "verifiedWindows": len(applications),
        "enabledParsers": sum(bool(item.get("enabled")) for item in sources),
        "programs": len(programs),
        "windowPolicies": len(policies),
        "predictedWindows": len(predictions),
    }
    return errors, summary
