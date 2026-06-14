from __future__ import annotations

import pytest

from gradwindow.intakes import intake_identity, parse_intake_details


def test_parse_structured_intake_details() -> None:
    assert parse_intake_details("Michaelmas 2027") == {
        "label": "Michaelmas 2027",
        "cycleYear": 2027,
        "academicYearEnd": None,
        "term": "michaelmas",
        "startMonth": 10,
    }
    assert parse_intake_details("2026/27")["academicYearEnd"] == 2027


def test_autumn_and_fall_have_the_same_identity() -> None:
    assert intake_identity({"intake": "Autumn 2027"}) == intake_identity(
        {"intake": "Fall 2027"}
    )


def test_intake_requires_a_year() -> None:
    with pytest.raises(ValueError, match="cycle year"):
        parse_intake_details("following fall")
