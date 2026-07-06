from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
import re

from .intakes import with_intake_details
from .io import read_json, write_json
from .paths import (
    APPLICATIONS_PATH,
    PREDICTIONS_PATH,
    PROGRAMME_CANDIDATES_PATH,
    PROGRAMS_PATH,
    WINDOW_CANDIDATES_PATH,
)
from .predictions import generate_predictions
from .validation import validate_data


def approve_window(
    candidate_id: str,
    reviewer: str,
    candidates_path: Path = WINDOW_CANDIDATES_PATH,
    applications_path: Path = APPLICATIONS_PATH,
) -> dict:
    candidates = read_json(candidates_path)
    candidate = next(
        (
            item
            for item in candidates.get("items", [])
            if item.get("id") == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise ValueError(f"Unknown candidate: {candidate_id}")
    if candidate.get("status", "pending") != "pending":
        raise ValueError(
            f"Candidate {candidate_id} is {candidate.get('status')}, not pending"
        )
    record = copy.deepcopy(candidate.get("record"))
    if not isinstance(record, dict):
        raise ValueError(f"Candidate {candidate_id} has no application record")
    record = with_intake_details(record)
    verified_at = datetime.now(timezone.utc).date().isoformat()
    record["verifiedAt"] = verified_at
    if candidate.get("type") == "parser-date-change":
        record["evidence"] = (
            f"{reviewer} reviewed the official source on {verified_at} and "
            f"confirmed an application window from {record['opensAt']} to "
            f"{record['closesAt']}."
        )

    applications = read_json(applications_path)
    proposed = [
        item for item in applications["applications"] if item["id"] != record["id"]
    ]
    proposed.append(record)
    proposed.sort(key=lambda item: (item["universityId"], item["closesAt"], item["id"]))
    proposed_payload = {
        **applications,
        "meta": {
            **applications["meta"],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
        "applications": proposed,
    }

    validation_path = applications_path.with_name(
        f"{applications_path.stem}.validation.json"
    )
    predictions_validation_path = applications_path.with_name(
        "predictions.validation.json"
    )
    write_json(validation_path, proposed_payload)
    try:
        generate_predictions(
            output_path=predictions_validation_path,
            applications_path=validation_path,
        )
        errors, _ = validate_data(
            applications_path=validation_path,
            predictions_path=predictions_validation_path,
        )
    finally:
        validation_path.unlink(missing_ok=True)
        predictions_validation_path.unlink(missing_ok=True)
    if errors:
        raise ValueError("Candidate failed validation: " + "; ".join(errors))

    write_json(applications_path, proposed_payload)
    prediction_output = (
        PREDICTIONS_PATH
        if applications_path == APPLICATIONS_PATH
        else applications_path.with_name("predictions.json")
    )
    generate_predictions(
        output_path=prediction_output,
        applications_path=applications_path,
    )
    candidate["status"] = "approved"
    candidate["reviewedBy"] = reviewer
    candidate["reviewedAt"] = datetime.now(timezone.utc).isoformat()
    write_json(candidates_path, candidates)
    return record


def approve_programme_candidates(
    *,
    university_id: str,
    reviewer: str,
    parsed_only: bool = True,
    candidates_path: Path = PROGRAMME_CANDIDATES_PATH,
    programs_path: Path = PROGRAMS_PATH,
    applications_path: Path = APPLICATIONS_PATH,
) -> dict[str, int]:
    candidates = read_json(candidates_path)
    programs_payload = read_json(programs_path)
    applications_payload = read_json(applications_path)
    known_program_ids = {item["id"] for item in programs_payload.get("programs", [])}
    known_application_ids = {
        item["id"] for item in applications_payload.get("applications", [])
    }
    approved_at = datetime.now(timezone.utc)
    verified_at = approved_at.date().isoformat()
    promoted_programmes = 0
    promoted_windows = 0

    for candidate in candidates.get("items", []):
        if candidate.get("type") != "new-programme":
            continue
        if candidate.get("universityId") != university_id:
            continue
        if candidate.get("status", "pending") != "pending":
            continue
        windows = candidate.get("windows") or []
        exact_windows = [
            window
            for window in windows
            if window.get("opensAt") and window.get("closesAt")
        ]
        if parsed_only and candidate.get("parseStatus") != "parsed":
            continue
        if not exact_windows:
            continue
        programme = copy.deepcopy(candidate.get("programme") or {})
        programme_id = programme.get("id")
        if not programme_id:
            continue
        programme["faculty"] = _dedupe_faculty(programme.get("faculty", ""))
        if programme_id not in known_program_ids:
            programs_payload.setdefault("programs", []).append(programme)
            known_program_ids.add(programme_id)
            promoted_programmes += 1
        for window in exact_windows:
            record_id = _programme_window_id(programme_id, window)
            if record_id in known_application_ids:
                continue
            record = with_intake_details(
                {
                    "id": record_id,
                    "universityId": university_id,
                    "scopeType": "programme",
                    "scopeId": programme_id,
                    "intake": window["intake"],
                    "round": window.get("round", ""),
                    "applicantCategories": window.get("applicantCategories", ["all"]),
                    "opensAt": window["opensAt"],
                    "closesAt": window["closesAt"],
                    "applicationUrl": programme["applicationUrl"],
                    "sourceUrl": programme["sourceUrl"],
                    "verifiedAt": verified_at,
                    "evidence": _programme_window_evidence(
                        programme["name"],
                        window,
                        programme["sourceUrl"],
                    ),
                }
            )
            applications_payload.setdefault("applications", []).append(record)
            known_application_ids.add(record_id)
            promoted_windows += 1
        if len(exact_windows) == len(windows):
            candidate["status"] = "approved"
            candidate["reviewedBy"] = reviewer
            candidate["reviewedAt"] = approved_at.isoformat()
        else:
            candidate["reviewNotes"] = (
                "Exact windows were promoted, but at least one window is missing "
                "an opening or closing date and still needs review."
            )

    if promoted_windows == 0:
        return {
            "promotedProgrammes": 0,
            "promotedWindows": 0,
            "remainingPending": _pending_count(candidates, university_id),
        }

    programs_payload["programs"].sort(key=lambda item: (item["universityId"], item["id"]))
    applications_payload["applications"].sort(
        key=lambda item: (item["universityId"], item["closesAt"], item["id"])
    )
    programs_payload["meta"] = {
        **programs_payload.get("meta", {}),
        "updatedAt": approved_at.date().isoformat(),
    }
    applications_payload["meta"] = {
        **applications_payload.get("meta", {}),
        "updatedAt": approved_at.isoformat(),
    }

    _validate_programme_promotion(programs_payload, applications_payload)

    write_json(programs_path, programs_payload)
    write_json(applications_path, applications_payload)
    candidates.setdefault("meta", {})["updatedAt"] = approved_at.isoformat()
    write_json(candidates_path, candidates)
    prediction_output = (
        PREDICTIONS_PATH
        if applications_path == APPLICATIONS_PATH
        else applications_path.with_name("predictions.json")
    )
    generate_predictions(
        output_path=prediction_output,
        applications_path=applications_path,
    )
    return {
        "promotedProgrammes": promoted_programmes,
        "promotedWindows": promoted_windows,
        "remainingPending": _pending_count(candidates, university_id),
    }


def _validate_programme_promotion(
    programs_payload: dict,
    applications_payload: dict,
) -> None:
    validation_programs_path = PROGRAMS_PATH.with_name("programs.validation.json")
    validation_applications_path = APPLICATIONS_PATH.with_name(
        "applications.validation.json"
    )
    validation_predictions_path = APPLICATIONS_PATH.with_name(
        "predictions.validation.json"
    )
    write_json(validation_programs_path, programs_payload)
    write_json(validation_applications_path, applications_payload)
    try:
        generate_predictions(
            output_path=validation_predictions_path,
            applications_path=validation_applications_path,
        )
        errors, _ = validate_data(
            programs_path=validation_programs_path,
            applications_path=validation_applications_path,
            predictions_path=validation_predictions_path,
        )
    finally:
        validation_programs_path.unlink(missing_ok=True)
        validation_applications_path.unlink(missing_ok=True)
        validation_predictions_path.unlink(missing_ok=True)
    if errors:
        raise ValueError(
            "Programme candidate promotion failed validation: " + "; ".join(errors)
        )


def _programme_window_id(programme_id: str, window: dict) -> str:
    intake_year = _intake_year(window.get("intake", "")) or window["closesAt"][:4]
    return f"{programme_id}-{intake_year}-{_slug(window.get('round') or 'main')}"


def _programme_window_evidence(programme_name: str, window: dict, source_url: str) -> str:
    return (
        f"The official programme page for {programme_name} lists "
        f"{window.get('round') or 'the application window'} opening on "
        f"{window['opensAt']} and closing on {window['closesAt']}. Source: {source_url}"
    )


def _dedupe_faculty(value: str) -> str:
    parts = [part.strip() for part in value.split("|") if part.strip()]
    deduped = list(dict.fromkeys(parts))
    return " | ".join(deduped)


def _intake_year(value: str) -> str | None:
    match = re.search(r"\b(20\d{2})\b", value)
    return match.group(1) if match else None


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _pending_count(candidates: dict, university_id: str) -> int:
    return sum(
        item.get("type") == "new-programme"
        and item.get("universityId") == university_id
        and item.get("status", "pending") == "pending"
        for item in candidates.get("items", [])
    )
