from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import read_json, write_json
from .paths import (
    ADAPTER_COMPLETION_REPORT_PATH,
    APPLICATIONS_PATH,
    PROGRAMME_CANDIDATES_PATH,
    PROGRAMME_CATALOG_STATE_PATH,
    PROGRAMS_PATH,
)
from .programme_adapters.base import ProgrammeAdapter
from .programme_adapters.registry import PROGRAMME_ADAPTERS
from .programme_windows import has_official_exact_window

AdapterFactory = Callable[[], ProgrammeAdapter]


def generate_adapter_completion_report(
    *,
    adapter_factories: Mapping[str, AdapterFactory] = PROGRAMME_ADAPTERS,
    catalog_state_path: Path = PROGRAMME_CATALOG_STATE_PATH,
    candidates_path: Path = PROGRAMME_CANDIDATES_PATH,
    programs_path: Path = PROGRAMS_PATH,
    applications_path: Path = APPLICATIONS_PATH,
    output_path: Path = ADAPTER_COMPLETION_REPORT_PATH,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Describe dedicated adapter progress without treating discovery as publication."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    catalog_states = read_json(catalog_state_path, {"universities": {}}).get(
        "universities", {}
    )
    candidates = read_json(candidates_path, {"items": []}).get("items", [])
    programs = read_json(programs_path, {"programs": []}).get("programs", [])
    applications = read_json(applications_path, {"applications": []}).get(
        "applications", []
    )

    candidates_by_university = _group_by_university(candidates)
    public_programmes = Counter(item["universityId"] for item in programs)
    public_windows = Counter(item["universityId"] for item in applications)
    rows = []
    for adapter_key, factory in sorted(adapter_factories.items()):
        adapter = factory()
        university_id = adapter.university_id
        state = catalog_states.get(university_id)
        university_candidates = candidates_by_university.get(university_id, [])
        windows = [
            window
            for candidate in university_candidates
            for window in candidate.get("windows", [])
        ]
        exact_count = sum(has_official_exact_window(window) for window in windows)
        missing_opening_count = sum(
            bool(window.get("closesAt")) and not window.get("opensAt")
            for window in windows
        )
        inferred_opening_count = sum(
            bool(window.get("opensAt"))
            and str(window.get("opensAtBasis", "")).startswith("inferred")
            for window in windows
        )
        unclassified_opening_count = sum(
            bool(window.get("opensAt"))
            and (
                "opensAtBasis" not in window
                or window.get("opensAtBasis") == "legacy-unclassified"
            )
            for window in windows
        )
        no_deadline_count = sum(
            not candidate.get("windows") for candidate in university_candidates
        )
        limitations = _limitations(
            state=state,
            window_count=len(windows),
            missing_opening_count=missing_opening_count,
            inferred_opening_count=inferred_opening_count,
            unclassified_opening_count=unclassified_opening_count,
        )
        rows.append(
            {
                "adapterKey": adapter_key,
                "universityId": university_id,
                "sourceUrl": state.get("sourceUrl") if state else adapter.catalog_url,
                "catalogueStatus": _catalogue_status(state),
                "catalogueProgrammeCount": state.get("itemCount", 0) if state else 0,
                "windowStatus": _window_status(
                    state=state,
                    window_count=len(windows),
                    exact_count=exact_count,
                    missing_opening_count=missing_opening_count,
                    inferred_opening_count=inferred_opening_count,
                ),
                "candidateWindowCount": len(windows),
                "exactWindowCount": exact_count,
                "missingOpeningDateCount": missing_opening_count,
                "inferredOpeningDateCount": inferred_opening_count,
                "unclassifiedOpeningBasisCount": unclassified_opening_count,
                "noDeadlineProgrammeCount": no_deadline_count,
                "pendingCandidateCount": sum(
                    candidate.get("status", "pending") == "pending"
                    for candidate in university_candidates
                ),
                "publishedProgrammeCount": public_programmes[university_id],
                "publishedWindowCount": public_windows[university_id],
                "integrationStatus": _integration_status(
                    public_programmes[university_id], public_windows[university_id]
                ),
                "limitations": limitations,
                "lastSuccessAt": state.get("checkedAt") if state else None,
            }
        )

    summary = {
        "registeredAdapters": len(rows),
        "cataloguesDiscovered": sum(
            row["catalogueStatus"] == "discovered" for row in rows
        ),
        "catalogueOnly": sum(row["windowStatus"] == "catalogue-only" for row in rows),
        "withExactWindowCandidates": sum(row["exactWindowCount"] > 0 for row in rows),
        "withMissingOpeningDates": sum(
            row["missingOpeningDateCount"] > 0 for row in rows
        ),
        "pendingCandidates": sum(row["pendingCandidateCount"] for row in rows),
        "exactWindowCandidates": sum(row["exactWindowCount"] for row in rows),
    }
    payload = {
        "meta": {
            "generatedAt": generated_at,
            "description": (
                "Machine-readable dedicated-adapter completion report. Discovery "
                "and candidate counts do not imply publication or maintainer review."
            ),
        },
        "summary": summary,
        "adapters": rows,
    }
    write_json(output_path, payload)
    return payload


def _group_by_university(
    items: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        university_id = item.get("universityId")
        if university_id:
            grouped.setdefault(university_id, []).append(item)
    return grouped


def _catalogue_status(state: dict[str, Any] | None) -> str:
    if state is None:
        return "not-run"
    if state.get("itemCount", 0) <= 0:
        return "empty"
    return "discovered"


def _window_status(
    *,
    state: dict[str, Any] | None,
    window_count: int,
    exact_count: int,
    missing_opening_count: int,
    inferred_opening_count: int,
) -> str:
    if state is None:
        return "not-run"
    if not window_count:
        return "catalogue-only"
    if exact_count and exact_count == window_count:
        return "exact-window-candidates"
    if exact_count:
        return "partial-exact-window-candidates"
    if missing_opening_count:
        return "closing-dates-only"
    if inferred_opening_count:
        return "inferred-openings-only"
    return "unclassified-window-candidates"


def _integration_status(programme_count: int, window_count: int) -> str:
    if window_count:
        return "published-windows"
    if programme_count:
        return "published-programmes-only"
    return "candidate-only"


def _limitations(
    *,
    state: dict[str, Any] | None,
    window_count: int,
    missing_opening_count: int,
    inferred_opening_count: int,
    unclassified_opening_count: int,
) -> list[dict[str, Any]]:
    limitations = []
    if state is None:
        limitations.append(
            {
                "code": "catalogue-not-run",
                "count": 1,
                "message": "Adapter has no successful catalogue snapshot.",
            }
        )
    elif not window_count:
        limitations.append(
            {
                "code": "no-window-candidates",
                "count": 1,
                "message": "Catalogue discovery produced no application-window candidates.",
            }
        )
    if missing_opening_count:
        limitations.append(
            {
                "code": "official-opening-date-missing",
                "count": missing_opening_count,
                "message": "Closing dates were found without exact official opening dates.",
            }
        )
    if inferred_opening_count:
        limitations.append(
            {
                "code": "opening-date-inferred",
                "count": inferred_opening_count,
                "message": "Opening dates use configured defaults and cannot be batch-promoted.",
            }
        )
    if unclassified_opening_count:
        limitations.append(
            {
                "code": "opening-basis-unclassified",
                "count": unclassified_opening_count,
                "message": "Legacy candidates have opening dates without opensAtBasis metadata.",
            }
        )
    return limitations
