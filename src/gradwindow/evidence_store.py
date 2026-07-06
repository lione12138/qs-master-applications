from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import read_json, write_json


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
    university_id = snapshot["universityId"]
    record_id = snapshot["recordId"]
    bundle = read_evidence_bundle(evidence_dir, university_id)
    bundle["universityId"] = university_id
    bundle.setdefault("snapshots", {})[record_id] = snapshot
    write_json(evidence_bundle_path(evidence_dir, university_id), bundle)
