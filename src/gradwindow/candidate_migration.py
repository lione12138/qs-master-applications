from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .candidate_review import attach_programme_candidate_evidence_hash
from .io import read_json, write_json
from .paths import (
    PROGRAMME_CANDIDATE_MIGRATION_REPORT_PATH,
    PROGRAMME_CANDIDATES_PATH,
)


def migrate_programme_candidate_metadata(
    *,
    candidates_path: Path = PROGRAMME_CANDIDATES_PATH,
    report_path: Path = PROGRAMME_CANDIDATE_MIGRATION_REPORT_PATH,
    migrated_at: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add explicit opening provenance and evidence hashes without inventing facts."""
    migrated_at = migrated_at or datetime.now(timezone.utc).isoformat()
    payload = read_json(candidates_path, {"meta": {}, "items": []})
    candidates_changed = 0
    missing_opening_basis = 0
    legacy_unclassified_basis = 0
    evidence_hashes_added = 0
    evidence_hashes_updated = 0

    for candidate in payload.get("items", []):
        changed = False
        for window in candidate.get("windows", []):
            if "opensAtBasis" in window:
                continue
            missing_opening_basis += 1
            if window.get("opensAt"):
                window["opensAtBasis"] = "legacy-unclassified"
                legacy_unclassified_basis += 1
            else:
                window["opensAtBasis"] = "missing"
            changed = True

        previous_hash = candidate.get("evidenceHash")
        attach_programme_candidate_evidence_hash(candidate)
        if previous_hash is None:
            evidence_hashes_added += 1
            changed = True
        elif previous_hash != candidate["evidenceHash"]:
            evidence_hashes_updated += 1
            changed = True
        if changed:
            candidates_changed += 1

    summary = {
        "candidateCount": len(payload.get("items", [])),
        "candidatesChanged": candidates_changed,
        "windowsMissingOpeningBasis": missing_opening_basis,
        "windowsMarkedLegacyUnclassified": legacy_unclassified_basis,
        "evidenceHashesAdded": evidence_hashes_added,
        "evidenceHashesUpdated": evidence_hashes_updated,
    }
    report = {
        "meta": {
            "generatedAt": migrated_at,
            "dryRun": dry_run,
            "description": (
                "Migration report for explicit programme-candidate opening provenance "
                "and evidence hashes. Legacy provenance is never upgraded to official."
            ),
        },
        "summary": summary,
    }
    if not dry_run:
        payload.setdefault("meta", {})["metadataMigratedAt"] = migrated_at
        payload["meta"]["metadataVersion"] = 2
        write_json(candidates_path, payload)
        write_json(report_path, report)
    return report
