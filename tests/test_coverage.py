from __future__ import annotations

import json

from gradwindow.coverage import generate_coverage, next_action


def test_generate_top200_coverage(tmp_path) -> None:
    output = tmp_path / "coverage.json"
    payload = generate_coverage(output_path=output)
    assert output.exists()
    assert payload["summary"]["targetUniversities"] == 200
    assert len(payload["universities"]) == 200
    assert len(payload["batches"]) == 40
    assert payload["batches"][0]["positions"] == [1, 5]
    assert payload["batches"][0]["policiesVerified"] == 5
    assert payload["batches"][1]["policiesVerified"] == 5
    assert payload["batches"][2]["policiesVerified"] == 5
    assert payload["batches"][3]["policiesVerified"] == 5
    assert payload["batches"][4]["policiesVerified"] == 5
    assert payload["batches"][5]["policiesVerified"] == 5
    assert payload["summary"]["policiesVerified"] >= 55
    assert payload["summary"]["universitiesWithPrograms"] >= 48
    assert payload["summary"]["predictedWindows"] >= 20
    assert payload["summary"]["verifiedWindows"] >= 20
    assert json.loads(output.read_text(encoding="utf-8"))["summary"] == payload[
        "summary"
    ]


def test_coverage_next_action_is_progressive() -> None:
    assert next_action(False, None, 0, 0) == "locate-official-entry"
    assert next_action(True, None, 0, 0) == "verify-window-policy"
    assert (
        next_action(True, {"model": "programme-specific"}, 0, 0)
        == "select-target-programmes"
    )
    assert (
        next_action(True, {"model": "programme-specific"}, 5, 0)
        == "verify-exact-windows"
    )
    assert (
        next_action(True, {"model": "programme-specific"}, 5, 2)
        == "monitor-and-refresh"
    )
