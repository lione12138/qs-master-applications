from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

from .io import read_json, write_json
from .monitor import check_university, summarize_monitor_results
from .paths import APPLICATIONS_PATH, APPLICATION_SOURCE_STATE_PATH


def monitor_application_sources(
    applications_path: Path = APPLICATIONS_PATH,
    state_path: Path = APPLICATION_SOURCE_STATE_PATH,
    workers: int = 8,
) -> dict[str, int]:
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
                {"homepageUrl": url},
                previous,
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
    for record in applications:
        result = dict(results_by_url[record["sourceUrl"]])
        result["recordId"] = record["id"]
        result["universityId"] = record["universityId"]
        entries[record["id"]] = result

    summary = summarize_monitor_results(entries)
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
