from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError

from .discovery import same_official_domain
from .io import read_json
from .models import (
    ApplicantCategory,
    ApplicationWindow,
    EvidenceSnapshot,
    ParserSource,
    Prediction,
    Programme,
    ProgrammeGroup,
    University,
    WindowPolicy,
)
from .paths import (
    APPLICANT_CATEGORIES_PATH,
    APPLICATIONS_PATH,
    EVIDENCE_DIR,
    PREDICTIONS_PATH,
    PROGRAMME_GROUPS_PATH,
    PROGRAMS_PATH,
    SOURCES_PATH,
    UNIVERSITIES_PATH,
    WINDOW_POLICIES_PATH,
)
from .predictions import (
    official_cycle_key,
    shift_date_one_year,
    shift_intake_one_year,
)

APPLICATION_FIELDS = {
    "id",
    "universityId",
    "scopeType",
    "scopeId",
    "intake",
    "intakeDetails",
    "round",
    "opensAt",
    "closesAt",
    "applicationUrl",
    "sourceUrl",
    "verifiedAt",
    "applicantCategories",
    "evidence",
}
WINDOW_SCOPE_TYPES = {"institution", "programme-group", "programme"}


def valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_model(
    model: type[BaseModel],
    item: object,
    label: str,
    errors: list[str],
) -> bool:
    try:
        model.model_validate(item)
        return True
    except ValidationError as exc:
        for detail in exc.errors(include_url=False):
            location = ".".join(str(part) for part in detail["loc"]) or "record"
            errors.append(f"{label}: {location}: {detail['msg']}")
        return False


def validate_data(
    universities_path: Path = UNIVERSITIES_PATH,
    applications_path: Path = APPLICATIONS_PATH,
    sources_path: Path = SOURCES_PATH,
    programs_path: Path = PROGRAMS_PATH,
    policies_path: Path = WINDOW_POLICIES_PATH,
    predictions_path: Path = PREDICTIONS_PATH,
    evidence_dir: Path = EVIDENCE_DIR,
    programme_groups_path: Path = PROGRAMME_GROUPS_PATH,
    applicant_categories_path: Path = APPLICANT_CATEGORIES_PATH,
) -> tuple[list[str], dict[str, int]]:
    university_payload = read_json(universities_path)
    application_payload = read_json(applications_path)
    universities = university_payload.get("universities")
    applications = application_payload.get("applications")
    sources_payload = read_json(sources_path)
    sources = sources_payload.get("sources")
    programs = read_json(programs_path).get("programs")
    programme_groups = read_json(programme_groups_path).get("groups")
    applicant_categories = read_json(applicant_categories_path).get("categories")
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
    if not isinstance(programme_groups, list):
        errors.append("programme groups must be a list")
        programme_groups = []
    if not isinstance(applicant_categories, list):
        errors.append("applicant categories must be a list")
        applicant_categories = []
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
        if not validate_model(University, item, label, errors):
            continue
        if label in university_ids:
            errors.append(f"{label}: duplicate university id")
        university_ids.add(label)
        university_domains[label] = item["officialDomains"]
        positions.append(item["qsPosition"])

    if sorted(positions) != list(range(1, 201)):
        errors.append("QS positions must be unique and cover 1 through 200")

    category_ids: set[str] = set()
    for item in applicant_categories:
        label = item.get("id", "unknown applicant category")
        if not validate_model(ApplicantCategory, item, label, errors):
            continue
        if label in category_ids:
            errors.append(f"{label}: duplicate applicant category id")
        category_ids.add(label)
    if "all" not in category_ids:
        errors.append("applicant categories must define all")

    group_ids: set[str] = set()
    groups_by_id: dict[str, dict] = {}
    for item in programme_groups:
        label = item.get("id", "unknown programme group")
        if not validate_model(ProgrammeGroup, item, label, errors):
            continue
        if label in group_ids:
            errors.append(f"{label}: duplicate programme group id")
        group_ids.add(label)
        groups_by_id[label] = item
        if item["universityId"] not in university_ids:
            errors.append(f"{label}: unknown universityId")

    application_ids: set[str] = set()
    program_ids: set[str] = set()
    programs_by_id: dict[str, dict] = {}
    for item in programs:
        label = item.get("id", "unknown programme")
        if not validate_model(Programme, item, label, errors):
            continue
        if label in program_ids:
            errors.append(f"{label}: duplicate programme id")
        program_ids.add(label)
        programs_by_id[label] = item
        if item["universityId"] not in university_ids:
            errors.append(f"{label}: unknown universityId")
        group_id = item.get("programmeGroupId")
        if group_id and group_id not in group_ids:
            errors.append(f"{label}: unknown programmeGroupId")
        if (
            group_id in groups_by_id
            and groups_by_id[group_id]["universityId"] != item["universityId"]
        ):
            errors.append(f"{label}: programme group belongs to another university")
        if item["universityId"] in university_domains and not same_official_domain(
            item["sourceUrl"], university_domains[item["universityId"]]
        ):
            errors.append(f"{label}: sourceUrl is outside official domains")

    application_keys: set[tuple] = set()
    for item in applications:
        label = item.get("id", "unknown application")
        if not validate_model(ApplicationWindow, item, label, errors):
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
            errors.append(f"{label}: institution scopeId must match universityId")
        if scope_type == "programme" and scope_id not in program_ids:
            errors.append(f"{label}: programme scope references an unknown programme")
        if scope_type == "programme-group" and scope_id not in group_ids:
            errors.append(f"{label}: programme-group scope references an unknown group")
        if (
            scope_type == "programme"
            and scope_id in programs_by_id
            and programs_by_id[scope_id]["universityId"] != item["universityId"]
        ):
            errors.append(f"{label}: programme scope belongs to another university")
        if (
            scope_type == "programme-group"
            and scope_id in groups_by_id
            and groups_by_id[scope_id]["universityId"] != item["universityId"]
        ):
            errors.append(
                f"{label}: programme-group scope belongs to another university"
            )
        unknown_categories = sorted(set(item["applicantCategories"]) - category_ids)
        if unknown_categories:
            errors.append(
                f"{label}: unknown applicant categories: "
                f"{', '.join(unknown_categories)}"
            )
        if item["universityId"] in university_domains and not same_official_domain(
            item["sourceUrl"], university_domains[item["universityId"]]
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
        if not validate_model(Prediction, item, label, errors):
            continue
        if label in prediction_ids:
            errors.append(f"{label}: duplicate prediction id")
        prediction_ids.add(label)
        source = applications_by_id.get(item["basedOnRecordId"])
        if source is None:
            errors.append(f"{label}: basedOnRecordId references an unknown window")
            continue
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
        unknown_categories = sorted(set(item["applicantCategories"]) - category_ids)
        if unknown_categories:
            errors.append(
                f"{label}: unknown applicant categories: "
                f"{', '.join(unknown_categories)}"
            )
        if item["intake"] != shift_intake_one_year(source["intake"]):
            errors.append(f"{label}: intake is not a one-year shift")
        if item["basedOnVerifiedAt"] != source["verifiedAt"]:
            errors.append(f"{label}: basedOnVerifiedAt must match its source window")
        if item["opensAt"] != shift_date_one_year(source["opensAt"]):
            errors.append(f"{label}: opensAt is not a one-year shift")
        if item["closesAt"] != shift_date_one_year(source["closesAt"]):
            errors.append(f"{label}: closesAt is not a one-year shift")
        prediction_key = official_cycle_key(item)
        if prediction_key in official_keys:
            errors.append(f"{label}: an official target-cycle window already exists")
        if prediction_key in prediction_keys:
            errors.append(f"{label}: duplicate predicted target window")
        prediction_keys.add(prediction_key)

    evidence_count = 0
    if applications_path == APPLICATIONS_PATH:
        for item in applications:
            evidence_path = evidence_dir / f"{item['id']}.json"
            if not evidence_path.exists():
                errors.append(f"{item['id']}: missing evidence snapshot")
                continue
            snapshot = read_json(evidence_path)
            if not validate_model(EvidenceSnapshot, snapshot, item["id"], errors):
                continue
            evidence_count += 1
            if snapshot["recordId"] != item["id"]:
                errors.append(f"{item['id']}: evidence recordId mismatch")
            if snapshot["universityId"] != item["universityId"]:
                errors.append(f"{item['id']}: evidence universityId mismatch")
            if snapshot["sourceUrl"] != item["sourceUrl"]:
                errors.append(f"{item['id']}: evidence sourceUrl mismatch")

    for index, source in enumerate(sources):
        label = source.get("recordId", f"source {index}")
        if not validate_model(ParserSource, source, label, errors):
            continue
        if not source.get("enabled"):
            continue
        if label not in application_ids:
            errors.append(f"{label}: enabled source references an unknown application")
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
        if not validate_model(WindowPolicy, policy, label, errors):
            continue
        if label in policy_ids:
            errors.append(f"{label}: duplicate window policy")
        policy_ids.add(label)
        if label not in university_ids:
            errors.append(f"{label}: policy references an unknown university")
        if label in university_domains and not same_official_domain(
            policy["sourceUrl"], university_domains[label]
        ):
            errors.append(f"{label}: policy sourceUrl is outside official domains")

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
        "programmeGroups": len(programme_groups),
        "applicantCategories": len(applicant_categories),
        "windowPolicies": len(policies),
        "predictedWindows": len(predictions),
        "evidenceSnapshots": evidence_count,
    }
    return errors, summary
