from __future__ import annotations

from gradwindow.programme_windows import (
    has_official_exact_window,
    programme_window_record_id,
)


def test_programme_window_record_ids_include_applicant_scope() -> None:
    window = {
        "intake": "September 2027",
        "round": "Main deadline",
        "applicantCategories": ["eu-efta"],
        "opensAt": "2026-10-15",
        "closesAt": "2027-04-01",
    }

    record_id = programme_window_record_id("example-msc", window)

    assert record_id == "example-msc-2027-main-deadline-eu-efta"
    assert programme_window_record_id(
        "example-msc",
        window,
        existing_ids={record_id},
    ).startswith(f"{record_id}-")


def test_official_exact_window_requires_explicit_official_basis() -> None:
    window = {
        "opensAt": "2026-10-15",
        "closesAt": "2027-04-01",
        "opensAtBasis": "official",
    }

    assert has_official_exact_window(window)
    assert not has_official_exact_window(
        {**window, "opensAtBasis": "inferred-cycle-default"}
    )
    assert not has_official_exact_window({**window, "opensAtBasis": None})
