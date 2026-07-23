from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Mapping
from typing import Any

from .intakes import with_intake_details
from .predictions import official_cycle_key


def has_official_exact_window(window: Mapping[str, Any]) -> bool:
    return bool(
        window.get("opensAt")
        and window.get("closesAt")
        and window.get("opensAtBasis") == "official"
    )


def programme_window_record_id(
    programme_id: str,
    window: Mapping[str, Any],
    *,
    existing_ids: Collection[str] = (),
) -> str:
    intake = str(window.get("intake", ""))
    closes_at = str(window.get("closesAt", ""))
    year_match = re.search(r"\b(20\d{2})\b", intake)
    year = year_match.group(1) if year_match else closes_at[:4] or "cycle"
    round_label = str(window.get("round") or "main")
    categories = sorted(str(value) for value in window.get("applicantCategories", []))

    base = f"{programme_id}-{year}-{_slug(round_label)}"
    if categories and categories != ["all"]:
        base = f"{base}-{_slug('-'.join(categories))}"
    if base not in existing_ids:
        return base

    identity = "|".join(
        (
            intake,
            round_label,
            ",".join(categories),
            str(window.get("opensAt", "")),
            closes_at,
        )
    )
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{suffix}"


def known_programme_window_candidates(
    adapter,
    programme,
    known_programme: Mapping[str, Any],
    shared_opens_at: str | None,
    applications_by_cycle: Mapping[tuple, dict],
    application_ids: Collection[str],
    detected_at: str,
) -> list[dict]:
    shared_opening_basis = getattr(adapter, "application_opens_at_basis", "official")
    scope_type = getattr(
        adapter,
        "known_programme_window_scope_type",
        "programme",
    )
    scope_id = getattr(adapter, "known_programme_window_scope_id", None) or programme.id
    candidates = []
    for window in programme.windows:
        opens_at = window.opens_at or shared_opens_at
        opening_basis = "official" if window.opens_at else shared_opening_basis
        if not opens_at or opens_at > window.closes_at or opening_basis != "official":
            continue
        source_url = window.source_url or programme.source_url
        record = with_intake_details(
            {
                "id": programme_window_record_id(
                    programme.id,
                    {
                        "intake": window.intake or adapter.intake,
                        "round": window.round,
                        "applicantCategories": window.applicant_categories,
                        "opensAt": opens_at,
                        "closesAt": window.closes_at,
                    },
                    existing_ids=application_ids,
                ),
                "universityId": adapter.university_id,
                "scopeType": scope_type,
                "scopeId": scope_id,
                "intake": window.intake or adapter.intake,
                "round": window.round,
                "applicantCategories": window.applicant_categories,
                "opensAt": opens_at,
                "closesAt": window.closes_at,
                "applicationUrl": (
                    programme.application_url or known_programme["applicationUrl"]
                ),
                "sourceUrl": source_url,
                "verifiedAt": detected_at[:10],
                "evidence": (
                    f"The official programme adapter observed {programme.name} "
                    f"opening on {opens_at} and closing on {window.closes_at}. "
                    f"Source: {source_url}"
                ),
            }
        )
        existing = applications_by_cycle.get(official_cycle_key(record))
        if existing is not None:
            record["id"] = existing["id"]
            changed_fields = {
                field: {"previous": existing.get(field), "observed": record.get(field)}
                for field in ("opensAt", "closesAt")
                if existing.get(field) != record.get(field)
            }
            if not changed_fields:
                continue
            candidate_type = "adapter-window-change"
        else:
            changed_fields = {}
            candidate_type = "adapter-new-window"

        candidate_id = (
            f"adapter-window:{record['id']}:{record['opensAt']}:{record['closesAt']}"
        )
        candidates.append(
            {
                "id": candidate_id,
                "type": candidate_type,
                "status": "pending",
                "universityId": adapter.university_id,
                "detectedAt": detected_at,
                "sourceUrl": source_url,
                "openingBasis": opening_basis,
                "record": record,
                "changes": changed_fields,
                "evidenceExcerpt": programme.deadline_text,
            }
        )
    return candidates


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")
