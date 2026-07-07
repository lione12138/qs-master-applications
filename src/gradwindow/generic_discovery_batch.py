from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import read_json, write_json
from .paths import (
    GENERIC_PROGRAMME_DISCOVERY_CONFIG_PATH,
    GENERIC_PROGRAMME_DISCOVERY_REPORT_PATH,
    PROGRAMME_CANDIDATES_PATH,
    UNIVERSITIES_PATH,
)
from .programme_adapters.generic import GenericProgrammeAdapter, GenericProgrammeConfig
from .programme_discovery import discover_programmes

COMING_SOON_REASONS = (
    "coming soon",
    "to be confirmed",
    "tba",
    "open soon",
    "applications will open",
)


def run_generic_discovery_batch(
    *,
    config_path: Path = GENERIC_PROGRAMME_DISCOVERY_CONFIG_PATH,
    report_path: Path = GENERIC_PROGRAMME_DISCOVERY_REPORT_PATH,
    candidates_path: Path = PROGRAMME_CANDIDATES_PATH,
    dry_run: bool = False,
    replace_existing: bool = False,
    only: set[str] | None = None,
) -> dict[str, Any]:
    config = read_json(config_path)
    universities = {
        item["id"]: item
        for item in read_json(UNIVERSITIES_PATH).get("universities", [])
    }
    entries = [
        entry
        for entry in config.get("schools", [])
        if entry.get("enabled", True)
        and (
            only is None
            or entry.get("universityId") in only
            or entry.get("name") in only
        )
    ]
    if replace_existing and not dry_run:
        _remove_pending_batch_candidates(candidates_path, entries)
    checked_at = datetime.now(timezone.utc).isoformat()
    results = []
    for entry in entries:
        university_id = entry["universityId"]
        try:
            university = universities[university_id]
            adapter = GenericProgrammeAdapter(
                GenericProgrammeConfig(
                    university_id=university_id,
                    school_prefix=entry.get("prefix") or _generic_prefix(university_id),
                    seed_urls=tuple(entry["seedUrls"]),
                    official_domains=tuple(
                        entry.get("officialDomains")
                        or university.get("officialDomains", [])
                    ),
                    default_application_url=(
                        entry.get("applicationUrl")
                        or university.get("admissionsUrl")
                        or university.get("homepageUrl")
                        or ""
                    ),
                    default_intake=entry.get("defaultIntake", "September 2026"),
                    default_application_opens_at=entry.get("defaultApplicationOpensAt"),
                    default_application_closes_at=entry.get(
                        "defaultApplicationClosesAt"
                    ),
                    default_deadline_evidence=entry.get("defaultDeadlineEvidence", ""),
                    application_opens_at_basis=entry.get(
                        "applicationOpensAtBasis", "inferred-cycle-default"
                    ),
                    minimum_closes_at=entry.get("minimumClosesAt", "2025-07-01"),
                    minimum_expected_programmes=int(entry.get("minimumExpected", 1)),
                    max_detail_pages=int(entry.get("maxDetailPages", 25)),
                    follow_application_links=bool(
                        entry.get("followApplicationLinks", False)
                    ),
                    exclude_url_patterns=tuple(entry.get("excludeUrlPatterns", [])),
                )
            )
            result = discover_programmes(
                adapter,
                candidates_path=candidates_path,
                dry_run=dry_run,
            )
            result["batchStatus"] = "ok"
        except Exception as exc:
            result = {
                "batchStatus": "error",
                "status": "error",
                "universityId": university_id,
                "sourceUrl": (entry.get("seedUrls") or [""])[0],
                "errorType": type(exc).__name__,
                "message": str(exc)[:400],
                "dryRun": dry_run,
            }
        results.append(result)

    candidates = read_json(candidates_path, {"items": []}).get("items", [])
    classifications = classify_generic_candidates(
        candidates,
        {entry["universityId"] for entry in entries},
        deadline_unavailable_university_ids={
            entry["universityId"]
            for entry in entries
            if entry.get("noDeadlineHandling") == "monitor"
        },
    )
    report = {
        "meta": {
            "updatedAt": checked_at,
            "dryRun": dry_run,
            "replaceExisting": replace_existing,
            "description": (
                "Batch generic programme discovery report. Candidates stay in "
                "data/ops/programme-candidates.json until reviewed."
            ),
        },
        "summary": {
            "schoolsConfigured": len(entries),
            "schoolsSucceeded": sum(
                item.get("batchStatus") == "ok" for item in results
            ),
            "schoolsErrored": sum(
                item.get("batchStatus") == "error" for item in results
            ),
            "readyToApprove": len(classifications["readyToApprove"]),
            "needsOpeningReview": len(classifications["needsOpeningReview"]),
            "needsOpeningDate": len(classifications["needsOpeningDate"]),
            "needsAdapter": len(classifications["needsAdapter"]),
            "comingSoonMonitor": len(classifications["comingSoonMonitor"]),
            "deadlineUnavailableMonitor": len(
                classifications["deadlineUnavailableMonitor"]
            ),
        },
        "results": results,
        "classification": classifications,
    }
    write_json(report_path, report)
    return report


def _remove_pending_batch_candidates(
    candidates_path: Path,
    entries: list[dict[str, Any]],
) -> None:
    targets = {
        (
            entry["universityId"],
            entry.get("prefix") or _generic_prefix(entry["universityId"]),
        )
        for entry in entries
    }
    payload = read_json(
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
    kept = []
    removed = 0
    for item in payload.get("items", []):
        candidate_id = item.get("id", "")
        item_target = item.get("universityId")
        should_remove = any(
            item_target == university_id
            and candidate_id.startswith(f"new-programme:{prefix}-")
            and item.get("status", "pending") == "pending"
            for university_id, prefix in targets
        )
        if should_remove:
            removed += 1
            continue
        kept.append(item)
    payload["items"] = kept
    payload.setdefault("meta", {})["lastBatchReplaceRemoved"] = removed
    payload["meta"]["updatedAt"] = datetime.now(timezone.utc).isoformat()
    write_json(candidates_path, payload)


def classify_generic_candidates(
    candidates: list[dict[str, Any]],
    university_ids: set[str],
    *,
    deadline_unavailable_university_ids: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    deadline_unavailable_university_ids = deadline_unavailable_university_ids or set()
    buckets: dict[str, list[dict[str, Any]]] = {
        "readyToApprove": [],
        "needsOpeningReview": [],
        "needsOpeningDate": [],
        "needsAdapter": [],
        "comingSoonMonitor": [],
        "deadlineUnavailableMonitor": [],
    }
    for item in candidates:
        if item.get("universityId") not in university_ids:
            continue
        if item.get("status", "pending") != "pending":
            continue
        summary = _candidate_summary(item)
        if _is_ready_to_approve(item):
            buckets["readyToApprove"].append(summary)
        elif _needs_opening_review(item):
            buckets["needsOpeningReview"].append(summary)
        elif _needs_opening_date(item):
            buckets["needsOpeningDate"].append(summary)
        elif _is_coming_soon(item):
            buckets["comingSoonMonitor"].append(summary)
        elif _is_deadline_unavailable(item, deadline_unavailable_university_ids):
            buckets["deadlineUnavailableMonitor"].append(summary)
        else:
            buckets["needsAdapter"].append(summary)
    for values in buckets.values():
        values.sort(key=lambda item: (item["universityId"], item["id"]))
    return buckets


def _candidate_summary(item: dict[str, Any]) -> dict[str, Any]:
    programme = item.get("programme", {})
    return {
        "id": item.get("id"),
        "universityId": item.get("universityId"),
        "programmeName": programme.get("name"),
        "sourceUrl": item.get("sourceUrl"),
        "windowCount": len(item.get("windows", [])),
        "parseStatus": item.get("parseStatus"),
        "reviewReason": item.get("reviewReason"),
    }


def _is_ready_to_approve(item: dict[str, Any]) -> bool:
    windows = item.get("windows", [])
    return (
        bool(windows)
        and item.get("parseStatus") == "parsed"
        and all(
            window.get("opensAt")
            and window.get("opensAtBasis") == "official"
            and window.get("closesAt")
            for window in windows
        )
    )


def _needs_opening_review(item: dict[str, Any]) -> bool:
    windows = item.get("windows", [])
    return (
        bool(windows)
        and item.get("parseStatus") == "parsed"
        and all(
            window.get("opensAt")
            and str(window.get("opensAtBasis", "")).startswith("inferred")
            and window.get("closesAt")
            for window in windows
        )
    )


def _needs_opening_date(item: dict[str, Any]) -> bool:
    windows = item.get("windows", [])
    return bool(windows) and all(
        not window.get("opensAt") and window.get("closesAt") for window in windows
    )


def _is_coming_soon(item: dict[str, Any]) -> bool:
    if item.get("windows"):
        return False
    text = " ".join(
        str(item.get(key, ""))
        for key in ("reviewReason", "evidenceExcerpt", "sourceUrl")
    ).lower()
    return any(marker in text for marker in COMING_SOON_REASONS)


def _is_deadline_unavailable(
    item: dict[str, Any],
    deadline_unavailable_university_ids: set[str],
) -> bool:
    if item.get("windows"):
        return False
    if item.get("universityId") in deadline_unavailable_university_ids:
        return True
    text = " ".join(
        str(item.get(key, ""))
        for key in ("reviewReason", "evidenceExcerpt", "sourceUrl")
    ).lower()
    return any(
        marker in text
        for marker in (
            "you can still apply",
            "applications for 20",
            "standard application deadlines",
        )
    )


def _generic_prefix(university_id: str) -> str:
    ignored = {"the", "university", "of", "and", "college", "institute"}
    parts = [part for part in university_id.split("-") if part not in ignored]
    return "-".join(parts[:3]) if parts else university_id.split("-", 1)[0]
