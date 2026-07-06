from __future__ import annotations

import concurrent.futures
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .content import evidence_matches_target_dates
from .evidence_store import evidence_snapshot_exists, write_evidence_snapshots
from .io import read_json, write_json
from .monitor import check_university, summarize_monitor_results
from .paths import (
    APPLICATION_SOURCE_STATE_PATH,
    APPLICATIONS_PATH,
    EVIDENCE_DIR,
)


def monitor_application_sources(
    applications_path: Path = APPLICATIONS_PATH,
    state_path: Path = APPLICATION_SOURCE_STATE_PATH,
    evidence_dir: Path | None = None,
    workers: int = 8,
) -> dict[str, int]:
    if evidence_dir is None:
        evidence_dir = (
            EVIDENCE_DIR
            if applications_path == APPLICATIONS_PATH
            else state_path.parent / "evidence"
        )
    applications = read_json(applications_path)["applications"]
    old_state = read_json(state_path, {"applications": {}})
    old_entries = old_state.get("applications", {})
    records_by_url: dict[str, list[dict]] = {}
    for record in applications:
        records_by_url.setdefault(record["sourceUrl"], []).append(record)

    results_by_url: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for url, records in records_by_url.items():
            previous = next(
                (
                    old_entries[record["id"]]
                    for record in records
                    if record["id"] in old_entries
                ),
                None,
            )
            future = executor.submit(
                check_university,
                {
                    "homepageUrl": url,
                    "evidenceDates": sorted(
                        {
                            value
                            for record in records
                            for value in (
                                record.get("opensAt"),
                                record.get("closesAt"),
                            )
                            if value
                        }
                    ),
                },
                previous,
                True,
            )
            future_map[future] = url
        for future in concurrent.futures.as_completed(future_map):
            url = future_map[future]
            try:
                results_by_url[url] = future.result()
            except Exception as exc:
                results_by_url[url] = {
                    "url": url,
                    "checkedAt": datetime.now(timezone.utc).isoformat(),
                    "status": "error",
                    "message": str(exc)[:240],
                    "changed": False,
                }

    entries = {}
    evidence_snapshots = []
    for record in applications:
        result = dict(results_by_url[record["sourceUrl"]])
        context = result.pop(
            "evidenceContext",
            {
                "excerpt": result.pop("evidenceExcerpt", ""),
                "contentSelector": "main|article|[role=main]|body",
                "matchedTextBefore": "",
                "matchedText": "",
                "matchedTextAfter": "",
            },
        )
        excerpt = context["excerpt"]
        result["recordId"] = record["id"]
        result["universityId"] = record["universityId"]
        entries[record["id"]] = result
        if result["status"] == "ok":
            target_dates = [
                value
                for value in _evidence_target_dates(record)
                if value
            ]
            if target_dates and not evidence_matches_target_dates(
                excerpt,
                target_dates,
            ):
                context_excerpt = "\n".join(
                    value
                    for value in (
                        context["matchedTextBefore"],
                        context["matchedText"],
                        context["matchedTextAfter"],
                    )
                    if value
                )
                if evidence_matches_target_dates(context_excerpt, target_dates):
                    excerpt = context_excerpt
                    context["excerpt"] = context_excerpt
                elif evidence_snapshot_exists(
                    evidence_dir,
                    record["universityId"],
                    record["id"],
                ):
                    continue
                else:
                    excerpt = ""
            evidence_snapshots.append(
                {
                    "recordId": record["id"],
                    "universityId": record["universityId"],
                    "sourceUrl": record["sourceUrl"],
                    "finalUrl": result["url"],
                    "capturedAt": result["checkedAt"],
                    "contentHash": result.get("contentHash"),
                    "contentType": result.get("contentType"),
                    "bytesRead": result.get("bytesRead"),
                    "truncated": result.get("truncated", False),
                    "excerpt": excerpt,
                    "excerptHash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                    "contentSelector": context["contentSelector"],
                    "matchedTextBefore": context["matchedTextBefore"],
                    "matchedText": context["matchedText"],
                    "matchedTextAfter": context["matchedTextAfter"],
                }
            )

    summary = summarize_monitor_results(entries)
    write_evidence_snapshots(evidence_dir, evidence_snapshots)
    write_json(
        state_path,
        {
            "meta": {
                "checkedAt": datetime.now(timezone.utc).isoformat(),
                "uniqueSourcePages": len(records_by_url),
                "summary": summary,
            },
            "applications": entries,
        },
    )
    return summary


def _evidence_target_dates(record: dict) -> tuple[str | None, ...]:
    if "configured cycle-default opening date" in record.get("evidence", ""):
        return (record.get("closesAt"),)
    return (record.get("opensAt"), record.get("closesAt"))
