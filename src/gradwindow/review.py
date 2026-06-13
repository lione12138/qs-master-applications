from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from .io import read_json, write_json
from .paths import (
    APPLICATIONS_PATH,
    MONITOR_STATE_PATH,
    REVIEW_QUEUE_PATH,
    ROOT,
    UNIVERSITIES_PATH,
)

REPORTS_DIR = ROOT / "reports"


def generate_review_outputs(
    monitor_path: Path = MONITOR_STATE_PATH,
    universities_path: Path = UNIVERSITIES_PATH,
    review_queue_path: Path = REVIEW_QUEUE_PATH,
    reports_dir: Path = REPORTS_DIR,
    source_state_path: Path | None = None,
    applications_path: Path = APPLICATIONS_PATH,
) -> tuple[Path, dict[str, int]]:
    monitor = read_json(monitor_path)
    universities = read_json(universities_path)["universities"]
    university_map = {item["id"]: item for item in universities}
    existing = read_json(review_queue_path, {"items": []})
    existing_by_id = {
        item["id"]: item
        for item in existing.get("items", [])
        if item.get("status") in {"pending", "investigating"}
    }
    entries = monitor.get("universities", {})
    now = datetime.now(timezone.utc).isoformat()

    for university_id, result in entries.items():
        university = university_map[university_id]
        monitor_error_id = f"monitor-error:{university_id}"
        if result.get("changed"):
            item_id = f"content-change:{university_id}:{result.get('contentHash', '')[:12]}"
            existing_by_id.setdefault(
                item_id,
                {
                    "id": item_id,
                    "type": "content-change",
                    "universityId": university_id,
                    "school": university["school"],
                    "qsRank": university["qsRank"],
                    "url": result["url"],
                    "reason": "Official page content changed consistently in two consecutive checks.",
                    "detectedAt": result["checkedAt"],
                    "status": "pending",
                },
            )
        elif result.get("status") in {"error", "http-error"}:
            existing_by_id[monitor_error_id] = {
                "id": monitor_error_id,
                "type": "monitor-error",
                "universityId": university_id,
                "school": university["school"],
                "qsRank": university["qsRank"],
                "url": result["url"],
                "reason": result.get("message")
                or f"HTTP status {result.get('httpStatus', 'unknown')}",
                "detectedAt": result["checkedAt"],
                "status": existing_by_id.get(monitor_error_id, {}).get(
                    "status", "pending"
                ),
            }
        else:
            existing_by_id.pop(monitor_error_id, None)

    if source_state_path is not None:
        source_state = read_json(source_state_path, {"applications": {}})
        application_map = {
            item["id"]: item
            for item in read_json(applications_path).get("applications", [])
        }
        for record_id, result in source_state.get("applications", {}).items():
            record = application_map.get(record_id)
            if not record:
                continue
            university = university_map[record["universityId"]]
            error_id = f"window-source-error:{record_id}"
            if result.get("changed"):
                item_id = (
                    f"window-source-change:{record_id}:"
                    f"{result.get('contentHash', '')[:12]}"
                )
                existing_by_id.setdefault(
                    item_id,
                    {
                        "id": item_id,
                        "type": "window-source-change",
                        "universityId": record["universityId"],
                        "recordId": record_id,
                        "school": university["school"],
                        "qsRank": university["qsRank"],
                        "url": result["url"],
                        "reason": (
                            "A published application-window source changed "
                            "consistently in two consecutive checks."
                        ),
                        "detectedAt": result["checkedAt"],
                        "status": "pending",
                    },
                )
            if result.get("status") in {"error", "http-error"}:
                existing_by_id[error_id] = {
                    "id": error_id,
                    "type": "window-source-error",
                    "universityId": record["universityId"],
                    "recordId": record_id,
                    "school": university["school"],
                    "qsRank": university["qsRank"],
                    "url": result["url"],
                    "reason": result.get("message")
                    or f"HTTP status {result.get('httpStatus', 'unknown')}",
                    "detectedAt": result["checkedAt"],
                    "status": existing_by_id.get(error_id, {}).get(
                        "status", "pending"
                    ),
                }
            else:
                existing_by_id.pop(error_id, None)

    items = sorted(
        existing_by_id.values(),
        key=lambda item: (item["type"] != "content-change", item["qsRank"]),
    )
    queue_payload = {
        "meta": {
            "generatedAt": now,
            "description": (
                "Automatic findings require maintainer review before publication."
            ),
        },
        "items": items,
    }
    write_json(review_queue_path, queue_payload)

    summary = {
        "confirmedChanges": sum(item["type"] == "content-change" for item in items),
        "monitorErrors": sum(item["type"] == "monitor-error" for item in items),
        "windowSourceChanges": sum(
            item["type"] == "window-source-change" for item in items
        ),
        "windowSourceErrors": sum(
            item["type"] == "window-source-error" for item in items
        ),
        "pendingReview": len(items),
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{date.today().isoformat()}.md"
    report_path.write_text(
        render_report(monitor, items, summary), encoding="utf-8"
    )
    return report_path, summary


def render_report(monitor: dict, items: list[dict], summary: dict[str, int]) -> str:
    monitor_summary = monitor["meta"]["summary"]
    rows = "\n".join(
        f"| {item['qsRank']} | {item['school']} | {item['type']} | "
        f"[official page]({item['url']}) | {item['reason']} |"
        for item in items
    )
    if not rows:
        rows = "| - | No pending review items | - | - | - |"
    return f"""# GradWindow daily report · {date.today().isoformat()}

## Monitor summary

- Checked: {monitor_summary['total']}
- Directly accessible: {monitor_summary['ok']}
- Blocked: {monitor_summary['blocked']}
- Errors: {monitor_summary['errors']}
- Confirmed content changes: {monitor_summary['changed']}
- Published-window source changes: {summary['windowSourceChanges']}
- Published-window source errors: {summary['windowSourceErrors']}
- Pending review items: {summary['pendingReview']}

## Review queue

| QS | University | Type | Source | Reason |
|---:|---|---|---|---|
{rows}

Automatic findings are not published as application deadlines until reviewed.
"""
