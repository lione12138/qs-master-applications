from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def select_due_adapter_keys(
    completion_report: dict[str, Any],
    *,
    tier: str,
    min_age_days: int,
    max_adapters: int,
    as_of: datetime | None = None,
) -> list[str]:
    """Select the stalest due adapters without maintaining another school list."""
    if tier not in {"active", "catalogue"}:
        raise ValueError(f"Unknown adapter schedule tier: {tier}")
    if min_age_days < 0:
        raise ValueError("min_age_days must not be negative")
    if max_adapters <= 0:
        raise ValueError("max_adapters must be positive")
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    cutoff = as_of - timedelta(days=min_age_days)

    due = []
    for row in completion_report.get("adapters", []):
        has_window_candidates = row.get("candidateWindowCount", 0) > 0
        if tier == "active" and not has_window_candidates:
            continue
        if tier == "catalogue" and has_window_candidates:
            continue
        last_success = _parse_timestamp(row.get("lastSuccessAt"))
        if last_success is not None and last_success > cutoff:
            continue
        due.append((last_success or datetime.min.replace(tzinfo=timezone.utc), row))

    due.sort(key=lambda value: (value[0], value[1]["adapterKey"]))
    return [row["adapterKey"] for _, row in due[:max_adapters]]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
