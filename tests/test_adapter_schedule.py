from datetime import datetime, timezone

import pytest

from gradwindow.adapter_schedule import select_due_adapter_keys


def _report() -> dict:
    return {
        "adapters": [
            {
                "adapterKey": "active-old",
                "candidateWindowCount": 2,
                "lastSuccessAt": "2026-07-01T00:00:00+00:00",
            },
            {
                "adapterKey": "active-fresh",
                "candidateWindowCount": 1,
                "lastSuccessAt": "2026-07-16T00:00:00+00:00",
            },
            {
                "adapterKey": "catalogue-never",
                "candidateWindowCount": 0,
                "lastSuccessAt": None,
            },
            {
                "adapterKey": "catalogue-old",
                "candidateWindowCount": 0,
                "lastSuccessAt": "2026-05-01T00:00:00+00:00",
            },
        ]
    }


def test_active_schedule_selects_only_stale_window_adapters() -> None:
    selected = select_due_adapter_keys(
        _report(),
        tier="active",
        min_age_days=7,
        max_adapters=8,
        as_of=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    assert selected == ["active-old"]


def test_catalogue_schedule_prioritises_never_run_then_oldest() -> None:
    selected = select_due_adapter_keys(
        _report(),
        tier="catalogue",
        min_age_days=30,
        max_adapters=2,
        as_of=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    assert selected == ["catalogue-never", "catalogue-old"]


def test_schedule_rejects_unbounded_or_unknown_inputs() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        select_due_adapter_keys(_report(), tier="other", min_age_days=7, max_adapters=1)
    with pytest.raises(ValueError, match="positive"):
        select_due_adapter_keys(
            _report(), tier="active", min_age_days=7, max_adapters=0
        )
