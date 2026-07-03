from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .http_client import DEFAULT_USER_AGENT, FetchFailure, fetch_page
from .io import read_json, write_json
from .paths import (
    APPLICATIONS_PATH,
    MONITOR_REPORT_PATH,
    SOURCES_PATH,
    WINDOW_CANDIDATES_PATH,
)

USER_AGENT = DEFAULT_USER_AGENT


def extract_iso_date(raw_html: str, pattern: str | None) -> str | None:
    if not pattern:
        return None
    match = re.search(pattern, raw_html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = match.group("date")
    datetime.strptime(value, "%Y-%m-%d")
    return value


def fetch(url: str) -> str:
    return fetch_page(url, user_agent=USER_AGENT, timeout=25).body


def update_deadlines(
    applications_path: Path = APPLICATIONS_PATH,
    sources_path: Path = SOURCES_PATH,
    report_path: Path = MONITOR_REPORT_PATH,
    candidates_path: Path = WINDOW_CANDIDATES_PATH,
    dry_run: bool = False,
) -> dict:
    payload = read_json(applications_path)
    source_config = read_json(sources_path)
    records = {item["id"]: item for item in payload["applications"]}
    candidate_payload = read_json(
        candidates_path,
        {
            "meta": {
                "description": (
                    "Internal exact-window candidates awaiting manual review."
                )
            },
            "items": [],
        },
    )
    existing_candidates = {
        item["id"]: item for item in candidate_payload.get("items", [])
    }
    report = {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "checked": 0,
        "changed": 0,
        "results": [],
    }

    for source in source_config["sources"]:
        if not source.get("enabled"):
            continue
        record_id = source["recordId"]
        result = {"recordId": record_id, "url": source["url"]}
        report["checked"] += 1
        if record_id not in records:
            result.update(status="error", message="Unknown recordId")
            report["results"].append(result)
            continue
        try:
            raw_html = fetch(source["url"])
            proposed = {}
            open_date = extract_iso_date(raw_html, source.get("openDateRegex"))
            close_date = extract_iso_date(raw_html, source.get("closeDateRegex"))
            if open_date and open_date != records[record_id]["opensAt"]:
                proposed["opensAt"] = open_date
            if close_date and close_date != records[record_id]["closesAt"]:
                proposed["closesAt"] = close_date
            candidate_open = proposed.get("opensAt", records[record_id]["opensAt"])
            candidate_close = proposed.get("closesAt", records[record_id]["closesAt"])
            if candidate_open > candidate_close:
                raise ValueError("Extracted opening date is after closing date")
            if proposed:
                proposed_record = {**records[record_id], **proposed}
                candidate_id = (
                    f"parser-change:{record_id}:"
                    f"{proposed_record['opensAt']}:{proposed_record['closesAt']}"
                )
                candidate = {
                    "id": candidate_id,
                    "type": "parser-date-change",
                    "status": "pending",
                    "detectedAt": report["checkedAt"],
                    "sourceUrl": source["url"],
                    "record": proposed_record,
                }
                if not dry_run:
                    existing_candidates[candidate_id] = candidate
                report["changed"] += 1
                result.update(
                    status="candidate-created" if not dry_run else "change-detected",
                    changes=proposed,
                    candidateId=candidate_id,
                )
            else:
                result.update(status="unchanged")
        except (
            IndexError,
            KeyError,
            OSError,
            ValueError,
            re.error,
            FetchFailure,
        ) as exc:
            result.update(status="error", message=str(exc))
        report["results"].append(result)

    if report["changed"] and not dry_run:
        candidate_payload["items"] = sorted(
            existing_candidates.values(),
            key=lambda item: (item.get("status") != "pending", item["id"]),
        )
        candidate_payload.setdefault("meta", {})["updatedAt"] = report["checkedAt"]
        write_json(candidates_path, candidate_payload)
    write_json(report_path, report)
    return report
