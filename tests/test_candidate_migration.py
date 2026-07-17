from pathlib import Path

from gradwindow.candidate_migration import migrate_programme_candidate_metadata
from gradwindow.candidate_review import programme_candidate_evidence_hash
from gradwindow.io import read_json, write_json


def test_candidate_migration_marks_unknown_provenance_without_claiming_official(
    tmp_path: Path,
) -> None:
    candidates_path = tmp_path / "programme-candidates.json"
    report_path = tmp_path / "report.json"
    write_json(
        candidates_path,
        {
            "meta": {},
            "items": [
                {
                    "id": "new-programme:example",
                    "type": "new-programme",
                    "status": "pending",
                    "universityId": "example-university",
                    "windows": [
                        {"opensAt": "2026-09-01", "closesAt": "2027-01-01"},
                        {"opensAt": None, "closesAt": "2027-02-01"},
                    ],
                }
            ],
        },
    )

    report = migrate_programme_candidate_metadata(
        candidates_path=candidates_path,
        report_path=report_path,
        migrated_at="2026-07-18T00:00:00+00:00",
    )

    candidate = read_json(candidates_path)["items"][0]
    assert candidate["windows"][0]["opensAtBasis"] == "legacy-unclassified"
    assert candidate["windows"][1]["opensAtBasis"] == "missing"
    assert candidate["evidenceHash"] == programme_candidate_evidence_hash(candidate)
    assert report["summary"] == {
        "candidateCount": 1,
        "candidatesChanged": 1,
        "windowsMissingOpeningBasis": 2,
        "windowsMarkedLegacyUnclassified": 1,
        "evidenceHashesAdded": 1,
        "evidenceHashesUpdated": 0,
    }
    assert read_json(report_path) == report


def test_candidate_migration_dry_run_does_not_write(tmp_path: Path) -> None:
    candidates_path = tmp_path / "programme-candidates.json"
    original = {"items": [{"id": "candidate", "windows": []}]}
    write_json(candidates_path, original)

    report = migrate_programme_candidate_metadata(
        candidates_path=candidates_path,
        report_path=tmp_path / "report.json",
        dry_run=True,
    )

    assert report["meta"]["dryRun"] is True
    assert read_json(candidates_path) == original
    assert not (tmp_path / "report.json").exists()
