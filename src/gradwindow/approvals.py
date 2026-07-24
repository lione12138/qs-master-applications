from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .evidence_store import write_evidence_snapshot
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
from .programme_windows import has_official_exact_window, programme_window_record_id
from .validation import validate_data


def approve_window(
    candidate_id: str,
    reviewer: str,
    candidates_path: Path = WINDOW_CANDIDATES_PATH,
    applications_path: Path = APPLICATIONS_PATH,
) -> dict:
    approved_at = datetime.now(timezone.utc)
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
    opening_basis = candidate.get("openingBasis")
    if opening_basis is not None and opening_basis != "official":
        raise ValueError(
            f"Candidate {candidate_id} does not have an official opening date"
        )
    record = with_intake_details(record)
    verified_at = approved_at.date().isoformat()
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

    suffix = uuid4().hex
    validation_path = applications_path.with_name(
        f"{applications_path.stem}.validation.{suffix}.json"
    )
    predictions_validation_path = applications_path.with_name(
        f"predictions.validation.{suffix}.json"
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
    if applications_path == APPLICATIONS_PATH:
        _write_window_candidate_evidence(record, candidate, approved_at)
    candidate["status"] = "approved"
    candidate["reviewedBy"] = reviewer
    candidate["reviewedAt"] = approved_at.isoformat()
    write_json(candidates_path, candidates)
    return record


def approve_official_adapter_window_candidates(
    *,
    reviewer: str,
    university_ids: set[str] | None = None,
    candidates_path: Path = WINDOW_CANDIDATES_PATH,
    applications_path: Path = APPLICATIONS_PATH,
) -> dict[str, int]:
    """Promote pending adapter windows that contain complete official dates."""
    approved_at = datetime.now(timezone.utc)
    verified_at = approved_at.date().isoformat()
    candidates = read_json(candidates_path)
    applications = read_json(applications_path)
    records_by_id = {
        item["id"]: copy.deepcopy(item) for item in applications.get("applications", [])
    }
    promoted: list[tuple[dict, dict]] = []

    for candidate in candidates.get("items", []):
        if candidate.get("status", "pending") != "pending":
            continue
        if candidate.get("type") not in {
            "adapter-new-window",
            "adapter-window-change",
        }:
            continue
        record = copy.deepcopy(candidate.get("record"))
        if not isinstance(record, dict):
            continue
        if (
            university_ids is not None
            and record.get("universityId") not in university_ids
        ):
            continue
        if candidate.get("openingBasis") != "official":
            continue
        if not all(
            record.get(field)
            for field in (
                "id",
                "universityId",
                "opensAt",
                "closesAt",
                "applicationUrl",
                "sourceUrl",
            )
        ):
            continue

        record = with_intake_details(record)
        record["verifiedAt"] = verified_at
        records_by_id[record["id"]] = record
        promoted.append((record, candidate))

    if not promoted:
        return {
            "promotedWindows": 0,
            "remainingPending": _pending_adapter_window_count(
                candidates, university_ids
            ),
        }

    proposed_payload = {
        **applications,
        "meta": {
            **applications.get("meta", {}),
            "updatedAt": approved_at.isoformat(),
        },
        "applications": sorted(
            records_by_id.values(),
            key=lambda item: (item["universityId"], item["closesAt"], item["id"]),
        ),
    }
    _validate_programme_promotion(read_json(PROGRAMS_PATH), proposed_payload)

    write_json(applications_path, proposed_payload)
    if applications_path == APPLICATIONS_PATH:
        for record, candidate in promoted:
            _write_window_candidate_evidence(record, candidate, approved_at)
    for _record, candidate in promoted:
        candidate["status"] = "approved"
        candidate["reviewedBy"] = reviewer
        candidate["reviewedAt"] = approved_at.isoformat()
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
        "promotedWindows": len(promoted),
        "remainingPending": _pending_adapter_window_count(candidates, university_ids),
    }


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
    evidence_records: list[tuple[dict, dict]] = []

    for candidate in candidates.get("items", []):
        if candidate.get("type") != "new-programme":
            continue
        if candidate.get("universityId") != university_id:
            continue
        if candidate.get("status", "pending") != "pending":
            continue
        windows = candidate.get("windows") or []
        exact_windows = [
            window for window in windows if has_official_exact_window(window)
        ]
        if parsed_only and (
            candidate.get("parseStatus") != "parsed" or not exact_windows
        ):
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
            record_id = programme_window_record_id(
                programme_id,
                window,
                existing_ids=known_application_ids,
            )
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
                    "sourceUrl": window.get("sourceUrl") or programme["sourceUrl"],
                    "verifiedAt": verified_at,
                    "evidence": _programme_window_evidence(
                        programme["name"],
                        window,
                        window.get("sourceUrl") or programme["sourceUrl"],
                    ),
                }
            )
            applications_payload.setdefault("applications", []).append(record)
            if applications_path == APPLICATIONS_PATH:
                evidence_records.append((record, candidate))
            known_application_ids.add(record_id)
            promoted_windows += 1
        if len(exact_windows) == len(windows):
            candidate["status"] = "approved"
            candidate["reviewedBy"] = reviewer
            candidate["reviewedAt"] = approved_at.isoformat()
        else:
            candidate["reviewNotes"] = (
                "Official exact windows were promoted, but at least one window "
                "is missing an official opening or closing date and still needs "
                "review."
            )

    if promoted_programmes == 0 and promoted_windows == 0:
        return {
            "promotedProgrammes": 0,
            "promotedWindows": 0,
            "remainingPending": _pending_count(candidates, university_id),
        }

    programs_payload["programs"].sort(
        key=lambda item: (item["universityId"], item["id"])
    )
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
    for record, candidate in evidence_records:
        _write_programme_candidate_evidence(record, candidate, approved_at)
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
    suffix = uuid4().hex
    validation_programs_path = PROGRAMS_PATH.with_name(
        f"programs.validation.{suffix}.json"
    )
    validation_applications_path = APPLICATIONS_PATH.with_name(
        f"applications.validation.{suffix}.json"
    )
    validation_predictions_path = APPLICATIONS_PATH.with_name(
        f"predictions.validation.{suffix}.json"
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


def _programme_window_evidence(
    programme_name: str, window: dict, source_url: str
) -> str:
    round_label = window.get("round") or "the application window"
    opens_at_basis = window.get("opensAtBasis", "official")
    if str(opens_at_basis).startswith("inferred"):
        opening_text = (
            f"uses {window['opensAt']} as the configured cycle-default opening date"
        )
    else:
        opening_text = f"lists {round_label} opening on {window['opensAt']}"
    return (
        f"The official programme page for {programme_name} lists {round_label} "
        f"closing on {window['closesAt']} and {opening_text}. "
        f"Source: {source_url}"
    )


def _write_programme_candidate_evidence(
    record: dict,
    candidate: dict,
    captured_at: datetime,
) -> None:
    excerpt = (candidate.get("evidenceExcerpt") or record["evidence"]).strip()
    excerpt_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    write_evidence_snapshot(
        APPLICATIONS_PATH.parent / "evidence",
        {
            "recordId": record["id"],
            "universityId": record["universityId"],
            "sourceUrl": record["sourceUrl"],
            "finalUrl": record["sourceUrl"],
            "capturedAt": captured_at.isoformat(),
            "contentHash": excerpt_hash,
            "contentType": "text/plain; charset=utf-8",
            "bytesRead": len(excerpt.encode("utf-8")),
            "truncated": False,
            "excerpt": excerpt,
            "excerptHash": excerpt_hash,
            "contentSelector": "programme-discovery-adapter",
            "matchedTextBefore": "",
            "matchedText": excerpt,
            "matchedTextAfter": "",
        },
    )


def _write_window_candidate_evidence(
    record: dict,
    candidate: dict,
    captured_at: datetime,
) -> None:
    excerpt = (
        candidate.get("evidenceExcerpt")
        or record.get("evidence")
        or (
            f"Approved exact application window from {record['opensAt']} to "
            f"{record['closesAt']}."
        )
    ).strip()
    excerpt_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    write_evidence_snapshot(
        APPLICATIONS_PATH.parent / "evidence",
        {
            "recordId": record["id"],
            "universityId": record["universityId"],
            "sourceUrl": record["sourceUrl"],
            "finalUrl": record["sourceUrl"],
            "capturedAt": captured_at.isoformat(),
            "contentHash": excerpt_hash,
            "contentType": "text/plain; charset=utf-8",
            "bytesRead": len(excerpt.encode("utf-8")),
            "truncated": False,
            "excerpt": excerpt,
            "excerptHash": excerpt_hash,
            "contentSelector": "window-approval-candidate",
            "matchedTextBefore": "",
            "matchedText": excerpt,
            "matchedTextAfter": "",
        },
    )


def _dedupe_faculty(value: str) -> str:
    parts = [part.strip() for part in value.split("|") if part.strip()]
    deduped = list(dict.fromkeys(parts))
    return " | ".join(deduped)


def _pending_count(candidates: dict, university_id: str) -> int:
    return sum(
        item.get("type") == "new-programme"
        and item.get("universityId") == university_id
        and item.get("status", "pending") == "pending"
        for item in candidates.get("items", [])
    )


def _pending_adapter_window_count(
    candidates: dict, university_ids: set[str] | None
) -> int:
    return sum(
        item.get("type") in {"adapter-new-window", "adapter-window-change"}
        and item.get("status", "pending") == "pending"
        and (
            university_ids is None
            or (item.get("record") or {}).get("universityId") in university_ids
        )
        for item in candidates.get("items", [])
    )
