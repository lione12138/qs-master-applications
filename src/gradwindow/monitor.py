from __future__ import annotations

import concurrent.futures
import hashlib
from io import BytesIO
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .content import (
    content_fingerprint,
    deadline_signal_text,
    evidence_context,
    extract_main_text,
)
from .http_client import DEFAULT_USER_AGENT, FetchFailure, fetch_page
from .io import read_json, write_json
from .paths import MONITOR_STATE_PATH, UNIVERSITIES_PATH

try:
    from pypdf import PdfReader
except ImportError:  # Compatibility for older local environments.
    from PyPDF2 import PdfReader

USER_AGENT = DEFAULT_USER_AGENT
TIMEOUT = 20
FINGERPRINT_VERSION = 3


def extract_fetched_text(page) -> str:
    if "application/pdf" not in page.content_type.lower():
        return page.body
    reader = PdfReader(BytesIO(page.raw_bytes))
    return "\n".join(
        text
        for pdf_page in reader.pages
        if (text := (pdf_page.extract_text() or "").strip())
    )


def evaluate_content_change(
    previous: dict | None,
    digest: str,
    fingerprint_version: int | None = None,
) -> dict:
    previous = previous or {}
    if (
        fingerprint_version is not None
        and previous.get("fingerprintVersion") != fingerprint_version
    ):
        return {
            "contentHash": digest,
            "changed": False,
            "changeDetected": False,
            "pendingContentHash": None,
            "pendingChangeCount": 0,
            "fingerprintVersion": fingerprint_version,
        }
    previous_hash = previous.get("contentHash")
    if not previous_hash or digest == previous_hash:
        result = {
            "contentHash": digest,
            "changed": False,
            "changeDetected": False,
            "pendingContentHash": None,
            "pendingChangeCount": 0,
        }
        if fingerprint_version is not None:
            result["fingerprintVersion"] = fingerprint_version
        return result

    pending_count = (
        int(previous.get("pendingChangeCount", 0)) + 1
        if previous.get("pendingContentHash") == digest
        else 1
    )
    changed = pending_count >= 2
    result = {
        "contentHash": digest if changed else previous_hash,
        "changed": changed,
        "changeDetected": True,
        "pendingContentHash": None if changed else digest,
        "pendingChangeCount": 0 if changed else pending_count,
    }
    if fingerprint_version is not None:
        result["fingerprintVersion"] = fingerprint_version
    return result


def check_university(
    university: dict,
    previous: dict | None,
    capture_evidence: bool = False,
) -> dict:
    url = university.get("admissionsUrl") or university["homepageUrl"]
    checked_at = datetime.now(timezone.utc).isoformat()
    first_seen = (previous or {}).get("firstSeenAt", checked_at)
    previous_success = previous_success_fields(previous)
    try:
        page = fetch_page(url, user_agent=USER_AGENT, timeout=TIMEOUT)
        fetched_text = extract_fetched_text(page)
        digest = content_fingerprint(fetched_text)
        signal_text = deadline_signal_text(fetched_text)
        signal_hash = (
            hashlib.sha256(signal_text.encode("utf-8")).hexdigest()
            if signal_text
            else None
        )
        change = evaluate_content_change(previous, digest, FINGERPRINT_VERSION)
        severity = None
        if change["changed"]:
            if capture_evidence or (
                signal_hash
                and signal_hash != (previous or {}).get("deadlineSignalHash")
            ):
                severity = "deadline"
            elif re.search(
                r"\bapplication|applications|admission|admissions\b",
                extract_main_text(fetched_text),
                flags=re.IGNORECASE,
            ):
                severity = "application"
            else:
                severity = "generic"
        result = {
            "url": page.final_url,
            "checkedAt": checked_at,
            "status": "ok",
            "httpStatus": page.status_code,
            "contentType": page.content_type,
            "bytesRead": page.bytes_read,
            "truncated": page.truncated,
            **change,
            "deadlineSignalHash": signal_hash,
            "changeSeverity": severity,
            "firstSeenAt": first_seen,
            "lastSuccessfulAt": checked_at,
        }
        if capture_evidence:
            result["evidenceContext"] = evidence_context(
                fetched_text,
                university.get("evidenceDates", []),
            )
        return result
    except FetchFailure as exc:
        return {
            "url": url,
            "checkedAt": checked_at,
            "status": (
                "blocked"
                if exc.kind in {"blocked", "rate-limited"}
                else "http-error"
                if exc.status_code is not None
                else "error"
            ),
            "errorKind": exc.kind,
            "httpStatus": exc.status_code,
            "changed": False,
            "firstSeenAt": first_seen,
            "message": str(exc)[:240],
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
        for key in (
            "contentHash",
            "lastSuccessfulAt",
            "fingerprintVersion",
            "deadlineSignalHash",
        )
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
