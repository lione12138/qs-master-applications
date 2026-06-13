from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .io import read_json, write_json
from .paths import MONITOR_STATE_PATH, UNIVERSITIES_PATH

USER_AGENT = "Mozilla/5.0 (compatible; GradWindowMonitor/1.0; daily admissions check)"
MAX_BYTES = 1_500_000
TIMEOUT = 20


def content_fingerprint(raw_html: str) -> str:
    text = re.sub(
        r"<(script|style|noscript|svg)\b[^>]*>.*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evaluate_content_change(previous: dict | None, digest: str) -> dict:
    previous = previous or {}
    previous_hash = previous.get("contentHash")
    if not previous_hash or digest == previous_hash:
        return {
            "contentHash": digest,
            "changed": False,
            "changeDetected": False,
            "pendingContentHash": None,
            "pendingChangeCount": 0,
        }

    pending_count = (
        int(previous.get("pendingChangeCount", 0)) + 1
        if previous.get("pendingContentHash") == digest
        else 1
    )
    changed = pending_count >= 2
    return {
        "contentHash": digest if changed else previous_hash,
        "changed": changed,
        "changeDetected": True,
        "pendingContentHash": None if changed else digest,
        "pendingChangeCount": 0 if changed else pending_count,
    }


def check_university(university: dict, previous: dict | None) -> dict:
    url = university.get("admissionsUrl") or university["homepageUrl"]
    checked_at = datetime.now(timezone.utc).isoformat()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    first_seen = (previous or {}).get("firstSeenAt", checked_at)
    previous_success = previous_success_fields(previous)
    try:
        with urllib.request.urlopen(
            request,
            timeout=TIMEOUT,
            context=ssl.create_default_context(),
        ) as response:
            body = response.read(MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            digest = content_fingerprint(body.decode(charset, errors="replace"))
            change = evaluate_content_change(previous, digest)
            return {
                "url": response.geturl(),
                "checkedAt": checked_at,
                "status": "ok",
                "httpStatus": response.status,
                **change,
                "firstSeenAt": first_seen,
                "lastSuccessfulAt": checked_at,
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "checkedAt": checked_at,
            "status": "blocked" if exc.code in {401, 403, 429} else "http-error",
            "httpStatus": exc.code,
            "changed": False,
            "firstSeenAt": first_seen,
            **previous_success,
        }
    except (OSError, ValueError) as exc:
        return {
            "url": url,
            "checkedAt": checked_at,
            "status": "error",
            "message": str(exc)[:240],
            "changed": False,
            "firstSeenAt": first_seen,
            **previous_success,
        }


def previous_success_fields(previous: dict | None) -> dict:
    if not previous:
        return {}
    return {
        key: previous[key]
        for key in ("contentHash", "lastSuccessfulAt")
        if previous.get(key)
    }


def monitor_universities(
    universities_path: Path = UNIVERSITIES_PATH,
    state_path: Path = MONITOR_STATE_PATH,
    workers: int = 16,
) -> dict:
    universities = read_json(universities_path)["universities"]
    old_state = read_json(state_path, {"universities": {}})
    old_entries = old_state.get("universities", {})
    results: dict[str, dict] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(check_university, item, old_entries.get(item["id"])): item
            for item in universities
        }
        for future in concurrent.futures.as_completed(future_map):
            university = future_map[future]
            try:
                results[university["id"]] = future.result()
            except Exception as exc:  # Keep one unusual site from aborting the scan.
                results[university["id"]] = {
                    "url": university.get("admissionsUrl")
                    or university["homepageUrl"],
                    "checkedAt": datetime.now(timezone.utc).isoformat(),
                    "status": "error",
                    "message": str(exc)[:240],
                    "changed": False,
                    "firstSeenAt": old_entries.get(university["id"], {}).get(
                        "firstSeenAt", datetime.now(timezone.utc).isoformat()
                    ),
                    **previous_success_fields(old_entries.get(university["id"])),
                }

    ordered = {
        item["id"]: results[item["id"]]
        for item in sorted(universities, key=lambda value: value["qsPosition"])
    }
    summary = summarize_monitor_results(ordered)
    payload = {
        "meta": {
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "policy": (
                "One low-frequency request per institution per day. Changes require "
                "review and do not automatically create deadlines."
            ),
            "summary": summary,
        },
        "universities": ordered,
    }
    write_json(state_path, payload)
    return summary


def summarize_monitor_results(results: dict[str, dict]) -> dict[str, int]:
    return {
        "total": len(results),
        "ok": sum(item["status"] == "ok" for item in results.values()),
        "changed": sum(item.get("changed", False) for item in results.values()),
        "blocked": sum(item["status"] == "blocked" for item in results.values()),
        "errors": sum(
            item["status"] in {"error", "http-error"} for item in results.values()
        ),
    }


def print_summary(summary: dict[str, int]) -> None:
    print(json.dumps(summary, ensure_ascii=False))
