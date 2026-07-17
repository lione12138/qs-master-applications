from __future__ import annotations

import hashlib
import json
from typing import Any

REVIEW_EVIDENCE_FIELDS = (
    "id",
    "type",
    "universityId",
    "sourceUrl",
    "programme",
    "windows",
    "parseStatus",
    "reviewReason",
    "evidenceExcerpt",
    "discoveryEvidence",
)


def programme_candidate_evidence_hash(candidate: dict[str, Any]) -> str:
    """Hash the immutable evidence-bearing portion of a programme candidate."""
    evidence = {
        field: candidate[field]
        for field in REVIEW_EVIDENCE_FIELDS
        if field in candidate
    }
    canonical = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def attach_programme_candidate_evidence_hash(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    candidate["evidenceHash"] = programme_candidate_evidence_hash(candidate)
    return candidate
