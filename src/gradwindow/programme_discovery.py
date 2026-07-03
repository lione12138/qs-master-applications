from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .http_client import DEFAULT_USER_AGENT, fetch_page
from .io import read_json, write_json
from .paths import (
    PROGRAMME_CANDIDATES_PATH,
    PROGRAMME_CATALOG_STATE_PATH,
    PROGRAMS_PATH,
)


def fetch_catalog(url: str) -> str:
    return fetch_page(url, user_agent=DEFAULT_USER_AGENT, timeout=30).body


def discover_programmes(
    adapter,
    *,
    programs_path: Path = PROGRAMS_PATH,
    candidates_path: Path = PROGRAMME_CANDIDATES_PATH,
    state_path: Path = PROGRAMME_CATALOG_STATE_PATH,
    fetcher: Callable[[str], str] = fetch_catalog,
    dry_run: bool = False,
) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    parse_with_fetcher = getattr(adapter, "parse_catalog_from_fetcher", None)
    if callable(parse_with_fetcher):
        catalog = parse_with_fetcher(fetcher)
    else:
        catalog = adapter.parse_catalog(fetcher(adapter.catalog_url))
    programs_payload = read_json(programs_path)
    known_ids = {
        item["id"]
        for item in programs_payload.get("programs", [])
        if item.get("universityId") == adapter.university_id
    }
    candidates_payload = read_json(
        candidates_path,
        {
            "meta": {
                "description": (
                    "Automatically discovered programme candidates awaiting "
                    "manual review. This file is not published."
                )
            },
            "items": [],
        },
    )
    existing = {item["id"]: item for item in candidates_payload.get("items", [])}
    created = 0
    for programme in catalog.programmes:
        if programme.id in known_ids:
            continue
        candidate_id = f"new-programme:{programme.id}"
        previous = existing.get(candidate_id)
        candidate = _candidate_record(
            adapter,
            programme,
            catalog.application_opens_at,
            checked_at,
        )
        if previous is None:
            created += 1
        else:
            candidate["status"] = previous.get("status", "pending")
            candidate["detectedAt"] = previous.get("detectedAt", checked_at)
            for key in ("reviewedAt", "reviewedBy", "reviewNotes"):
                if key in previous:
                    candidate[key] = previous[key]
        existing[candidate_id] = candidate

    items = sorted(
        existing.values(),
        key=lambda item: (item.get("status") != "pending", item["id"]),
    )
    snapshot_items = {
        programme.id: {
            "name": programme.name,
            "degreeType": programme.degree_type,
            "faculty": programme.faculty,
            "department": programme.department,
            "parseStatus": programme.parse_status,
            "deadlineHash": _hash(
                json.dumps(
                    [
                        {
                            "round": window.round,
                            "closesAt": window.closes_at,
                            "applicantCategories": window.applicant_categories,
                        }
                        for window in programme.windows
                    ],
                    sort_keys=True,
                )
            ),
        }
        for programme in catalog.programmes
    }
    state_payload = read_json(state_path, {"meta": {}, "universities": {}})
    state_payload.setdefault("universities", {})[adapter.university_id] = {
        "sourceUrl": adapter.catalog_url,
        "checkedAt": checked_at,
        "itemCount": len(catalog.programmes),
        "applicationOpensAt": catalog.application_opens_at,
        "catalogHash": _hash(json.dumps(snapshot_items, sort_keys=True)),
        "programmes": snapshot_items,
    }
    state_payload["meta"] = {
        "updatedAt": checked_at,
        "description": "Latest official programme-catalog discovery snapshots.",
    }

    if not dry_run:
        candidates_payload["items"] = items
        candidates_payload.setdefault("meta", {})["updatedAt"] = checked_at
        write_json(candidates_path, candidates_payload)
        write_json(state_path, state_payload)

    return {
        "status": "ok",
        "universityId": adapter.university_id,
        "sourceUrl": adapter.catalog_url,
        "checkedAt": checked_at,
        "catalogProgrammes": len(catalog.programmes),
        "knownProgrammes": len(known_ids),
        "newCandidates": created,
        "pendingCandidates": sum(
            item.get("status", "pending") == "pending"
            and item.get("universityId") == adapter.university_id
            for item in items
        ),
        "programmesWithoutDeadlines": sum(
            not programme.windows for programme in catalog.programmes
        ),
        "programmesNeedingReview": sum(
            programme.parse_status != "parsed" for programme in catalog.programmes
        ),
        "dryRun": dry_run,
    }


def _candidate_record(
    adapter,
    programme,
    shared_opens_at: str | None,
    detected_at: str,
) -> dict:
    def opening_for(window) -> str | None:
        opens_at = window.opens_at or shared_opens_at
        return opens_at if opens_at and opens_at <= window.closes_at else None

    windows = [
        {
            "intake": window.intake or adapter.intake,
            "round": window.round,
            "applicantCategories": window.applicant_categories,
            "opensAt": opening_for(window),
            "closesAt": window.closes_at,
        }
        for window in programme.windows
    ]
    has_unresolved_opening = any(window["opensAt"] is None for window in windows)
    deadline_precedes_shared_opening = bool(
        shared_opens_at
        and any(window["closesAt"] < shared_opens_at for window in windows)
    )
    return {
        "id": f"new-programme:{programme.id}",
        "type": "new-programme",
        "status": "pending",
        "universityId": adapter.university_id,
        "detectedAt": detected_at,
        "sourceUrl": programme.source_url,
        "programme": {
            "id": programme.id,
            "universityId": adapter.university_id,
            "name": programme.name,
            "degreeType": programme.degree_type,
            "faculty": " | ".join(
                value for value in (programme.faculty, programme.department) if value
            ),
            "applicationUrl": programme.application_url,
            "sourceUrl": programme.source_url,
        },
        "windows": windows,
        "parseStatus": programme.parse_status,
        "reviewReason": (
            "No application deadline was parsed."
            if not windows
            else (
                (
                    "An early deadline precedes the shared commencement date; "
                    "confirm the programme-specific opening date."
                )
                if deadline_precedes_shared_opening
                else (
                    "At least one opening date is not published as an exact date; "
                    "confirm it on the programme page."
                )
                if has_unresolved_opening
                else "Review the automatically discovered programme and application rounds."
            )
        ),
        "evidenceExcerpt": programme.deadline_text,
    }


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
