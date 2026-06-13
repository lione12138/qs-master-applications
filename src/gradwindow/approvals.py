from __future__ import annotations

from datetime import datetime, timezone
import copy
from pathlib import Path

from .io import read_json, write_json
from .paths import APPLICATIONS_PATH, PREDICTIONS_PATH, WINDOW_CANDIDATES_PATH
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
        (item for item in candidates.get("items", []) if item.get("id") == candidate_id),
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
