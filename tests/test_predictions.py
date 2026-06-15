from __future__ import annotations

import copy
import json

from gradwindow.paths import APPLICATIONS_PATH
from gradwindow.predictions import (
    generate_predictions,
    shift_date_one_year,
    shift_intake_one_year,
)


def test_shift_helpers_handle_years_and_leap_days() -> None:
    assert shift_date_one_year("2024-02-29") == "2025-02-28"
    assert shift_intake_one_year("Michaelmas 2026") == "Michaelmas 2027"
    assert shift_intake_one_year("2026/2027 cycle") == "2027/2028 cycle"
    assert shift_intake_one_year("2026/27 cycle") == "2027/28 cycle"


def test_current_windows_generate_next_cycle_predictions(tmp_path) -> None:
    output = tmp_path / "predictions.json"
    payload = generate_predictions(output_path=output)
    applications = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    assert len(payload["predictions"]) == len(applications["applications"])
    cambridge = next(
        item
        for item in payload["predictions"]
        if item["basedOnRecordId"]
        == "cambridge-advanced-computer-science-michaelmas-2026"
    )
    assert cambridge["intake"] == "Michaelmas 2027"
    assert cambridge["opensAt"] == "2026-09-03"
    assert cambridge["closesAt"] == "2027-02-26"
    assert cambridge["confidence"] == "low"
    assert cambridge["evidenceCycleCount"] == 1
    assert cambridge["methodology"] == "calendar-date-shift-plus-one-year"
    assert "not a forecast" in cambridge["disclaimer"]
    tsinghua = next(
        item
        for item in payload["predictions"]
        if item["basedOnRecordId"]
        == "tsinghua-advanced-computing-autumn-2026-round-2"
    )
    assert tsinghua["intake"] == "Autumn 2027"
    assert tsinghua["opensAt"] == "2027-01-01"
    assert tsinghua["closesAt"] == "2027-02-27"
    assert tsinghua["confidence"] == "low"
    kth = next(
        item
        for item in payload["predictions"]
        if item["basedOnRecordId"] == "kth-computer-science-autumn-2027"
    )
    assert kth["intake"] == "Autumn 2028"
    assert kth["opensAt"] == "2027-10-16"
    assert kth["closesAt"] == "2028-01-15"
    assert payload["meta"]["official"] is False


def test_official_target_cycle_replaces_the_matching_prediction(tmp_path) -> None:
    applications = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    source = next(
        item
        for item in applications["applications"]
        if item["id"] == "eth-autumn-2026-international-bachelors"
    )
    official = copy.deepcopy(source)
    official.update(
        {
            "id": "eth-autumn-2027-international-bachelors",
            "intake": "Fall 2027",
            "opensAt": "2026-11-02",
            "closesAt": "2026-11-30",
            "verifiedAt": "2026-08-01",
            "evidence": "Official target-cycle fixture.",
        }
    )
    applications["applications"].append(official)
    applications_path = tmp_path / "applications.json"
    applications_path.write_text(
        json.dumps(applications, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = generate_predictions(
        output_path=tmp_path / "predictions.json",
        applications_path=applications_path,
    )
    matching_2027 = [
        item
        for item in payload["predictions"]
        if item["universityId"] == source["universityId"]
        and item["round"] == source["round"]
        and item["intake"] == "Autumn 2027"
    ]
    assert matching_2027 == []
    assert any(
        item["basedOnRecordId"] == official["id"]
        and item["intake"] == "Fall 2028"
        for item in payload["predictions"]
    )


def test_repeated_historical_cycles_raise_prediction_confidence(tmp_path) -> None:
    applications = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    source = next(
        item
        for item in applications["applications"]
        if item["id"] == "cambridge-advanced-computer-science-michaelmas-2026"
    )
    previous = copy.deepcopy(source)
    previous.update(
        {
            "id": "cambridge-advanced-computer-science-michaelmas-2025",
            "intake": "Michaelmas 2025",
            "opensAt": "2024-09-03",
            "closesAt": "2025-02-26",
            "verifiedAt": "2025-06-14",
        }
    )
    applications["applications"].append(previous)
    applications_path = tmp_path / "applications.json"
    applications_path.write_text(json.dumps(applications), encoding="utf-8")

    payload = generate_predictions(
        output_path=tmp_path / "predictions.json",
        applications_path=applications_path,
    )
    prediction = next(
        item
        for item in payload["predictions"]
        if item["basedOnRecordId"] == source["id"]
    )
    assert prediction["confidence"] == "medium"
    assert prediction["evidenceCycleCount"] == 2
