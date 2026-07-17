from pathlib import Path

from gradwindow.adapter_completion import generate_adapter_completion_report
from gradwindow.io import read_json, write_json


class _Adapter:
    university_id = "example-university"
    catalog_url = "https://example.edu/catalogue"


def test_completion_report_keeps_discovery_and_publication_separate(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "catalog-state.json"
    candidates_path = tmp_path / "candidates.json"
    programs_path = tmp_path / "programs.json"
    applications_path = tmp_path / "applications.json"
    output_path = tmp_path / "report.json"
    write_json(
        state_path,
        {
            "universities": {
                "example-university": {
                    "sourceUrl": "https://example.edu/catalogue",
                    "checkedAt": "2026-07-17T00:00:00+00:00",
                    "itemCount": 2,
                }
            }
        },
    )
    write_json(
        candidates_path,
        {
            "items": [
                {
                    "id": "new-programme:one",
                    "status": "pending",
                    "universityId": "example-university",
                    "windows": [
                        {
                            "opensAt": "2026-09-01",
                            "opensAtBasis": "official",
                            "closesAt": "2027-01-01",
                        },
                        {
                            "opensAt": None,
                            "opensAtBasis": "missing",
                            "closesAt": "2027-02-01",
                        },
                    ],
                },
                {
                    "id": "new-programme:two",
                    "status": "pending",
                    "universityId": "example-university",
                    "windows": [],
                },
            ]
        },
    )
    write_json(programs_path, {"programs": []})
    write_json(applications_path, {"applications": []})

    payload = generate_adapter_completion_report(
        adapter_factories={"example": _Adapter},
        catalog_state_path=state_path,
        candidates_path=candidates_path,
        programs_path=programs_path,
        applications_path=applications_path,
        output_path=output_path,
        generated_at="2026-07-17T01:00:00+00:00",
    )

    row = payload["adapters"][0]
    assert row["catalogueStatus"] == "discovered"
    assert row["windowStatus"] == "partial-exact-window-candidates"
    assert row["exactWindowCount"] == 1
    assert row["missingOpeningDateCount"] == 1
    assert row["noDeadlineProgrammeCount"] == 1
    assert row["integrationStatus"] == "candidate-only"
    assert row["lastSuccessAt"] == "2026-07-17T00:00:00+00:00"
    assert row["limitations"] == [
        {
            "code": "official-opening-date-missing",
            "count": 1,
            "message": "Closing dates were found without exact official opening dates.",
        }
    ]
    assert read_json(output_path) == payload


def test_completion_report_marks_adapter_without_snapshot_as_not_run(
    tmp_path: Path,
) -> None:
    for name, payload in (
        ("catalog-state.json", {"universities": {}}),
        ("candidates.json", {"items": []}),
        ("programs.json", {"programs": []}),
        ("applications.json", {"applications": []}),
    ):
        write_json(tmp_path / name, payload)

    payload = generate_adapter_completion_report(
        adapter_factories={"example": _Adapter},
        catalog_state_path=tmp_path / "catalog-state.json",
        candidates_path=tmp_path / "candidates.json",
        programs_path=tmp_path / "programs.json",
        applications_path=tmp_path / "applications.json",
        output_path=tmp_path / "report.json",
    )

    row = payload["adapters"][0]
    assert row["catalogueStatus"] == "not-run"
    assert row["windowStatus"] == "not-run"
    assert row["limitations"][0]["code"] == "catalogue-not-run"
