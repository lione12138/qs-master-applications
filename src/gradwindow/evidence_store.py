from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .io import read_json, write_json

_BUNDLE_LOCKS: dict[Path, threading.Lock] = {}
_BUNDLE_LOCKS_GUARD = threading.Lock()


def evidence_bundle_path(evidence_dir: Path, university_id: str) -> Path:
    return evidence_dir / f"{university_id}.json"


def _legacy_snapshot_path(evidence_dir: Path, record_id: str) -> Path:
    return evidence_dir / f"{record_id}.json"


def read_evidence_bundle(evidence_dir: Path, university_id: str) -> dict[str, Any]:
    path = evidence_bundle_path(evidence_dir, university_id)
    payload = read_json(
        path,
        {
            "universityId": university_id,
            "snapshots": {},
        },
    )
    if "snapshots" not in payload:
        # Backward-compatible handling for the old one-file-per-record layout.
        return {
            "universityId": university_id,
            "snapshots": {
                payload["recordId"]: payload,
            },
        }
    return payload


def read_evidence_snapshot(
    evidence_dir: Path,
    university_id: str,
    record_id: str,
) -> dict[str, Any] | None:
    bundle = read_evidence_bundle(evidence_dir, university_id)
    snapshot = bundle.get("snapshots", {}).get(record_id)
    if snapshot is not None:
        return snapshot

    legacy_path = _legacy_snapshot_path(evidence_dir, record_id)
    if legacy_path.exists():
        return read_json(legacy_path)
    return None


def evidence_snapshot_exists(
    evidence_dir: Path,
    university_id: str,
    record_id: str,
) -> bool:
    return read_evidence_snapshot(evidence_dir, university_id, record_id) is not None


def write_evidence_snapshot(evidence_dir: Path, snapshot: dict[str, Any]) -> None:
    write_evidence_snapshots(evidence_dir, [snapshot])


def write_evidence_snapshots(
    evidence_dir: Path,
    snapshots: list[dict[str, Any]],
) -> None:
    snapshots_by_university: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        snapshots_by_university.setdefault(snapshot["universityId"], []).append(
            snapshot
        )
    for university_id, university_snapshots in snapshots_by_university.items():
        _write_university_evidence_snapshots(
            evidence_dir,
            university_id,
            university_snapshots,
        )


def _write_university_evidence_snapshots(
    evidence_dir: Path,
    university_id: str,
    snapshots: list[dict[str, Any]],
) -> None:
    path = evidence_bundle_path(evidence_dir, university_id).resolve()
    lock = _bundle_lock(path)
    with lock:
        bundle = read_evidence_bundle(evidence_dir, university_id)
        bundle["universityId"] = university_id
        bundle_snapshots = bundle.setdefault("snapshots", {})
        for snapshot in snapshots:
            bundle_snapshots[snapshot["recordId"]] = snapshot
        write_json(evidence_bundle_path(evidence_dir, university_id), bundle)


def _bundle_lock(path: Path) -> threading.Lock:
    with _BUNDLE_LOCKS_GUARD:
        lock = _BUNDLE_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _BUNDLE_LOCKS[path] = lock
        return lock
