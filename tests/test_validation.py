from __future__ import annotations

import copy
import json

import gradwindow.evidence_store as evidence_store
import gradwindow.validation as validation
from gradwindow.paths import APPLICATIONS_PATH, UNIVERSITIES_PATH
from gradwindow.predictions import generate_predictions
from gradwindow.validation import valid_http_url, validate_data


def test_current_public_data_is_valid() -> None:
    errors, summary = validate_data(UNIVERSITIES_PATH, APPLICATIONS_PATH)
    assert errors == []
    assert summary["universities"] == 200
    assert summary["curatedAdmissions"] >= 80
    assert summary["windowPolicies"] >= 80
    assert summary["programs"] >= 78
    assert summary["programmeGroups"] >= 74
    assert summary["applicantCategories"] >= 8
    assert summary["verifiedWindows"] >= 27
    assert summary["predictedWindows"] >= 27
    assert summary["evidenceSnapshots"] >= 27
    assert summary["legacyConfiguredOpeningWindows"] == sum(
        "configured cycle-default opening date" in item.get("evidence", "")
        for item in json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))[
            "applications"
        ]
    )


def test_http_url_validation() -> None:
    assert valid_http_url("https://example.edu/admissions")
    assert not valid_http_url("javascript:alert(1)")
    assert not valid_http_url("")


def test_validation_reads_each_university_evidence_bundle_once(monkeypatch) -> None:
    applications = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))[
        "applications"
    ]
    expected_universities = {item["universityId"] for item in applications}
    original_read = evidence_store.read_evidence_bundle
    calls: list[str] = []

    def tracked_read(evidence_dir, university_id):
        calls.append(university_id)
        return original_read(evidence_dir, university_id)

    monkeypatch.setattr(evidence_store, "read_evidence_bundle", tracked_read)
    monkeypatch.setattr(validation, "read_evidence_bundle", tracked_read)

    errors, summary = validate_data()

    assert errors == []
    assert summary["evidenceSnapshots"] == len(applications)
    assert len(calls) == len(expected_universities)
    assert set(calls) == expected_universities


def test_validation_rejects_cross_university_programme_scope(tmp_path) -> None:
    payload = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    record = payload["applications"][0]
    record["universityId"] = "eth-zurich-swiss-federal-institute-of-technology"
    applications_path = tmp_path / "applications.json"
    predictions_path = tmp_path / "predictions.json"
    applications_path.write_text(json.dumps(payload), encoding="utf-8")
    generate_predictions(predictions_path, applications_path)

    errors, _ = validate_data(
        applications_path=applications_path,
        predictions_path=predictions_path,
    )
    assert any(
        "programme scope belongs to another university" in error for error in errors
    )


def test_validation_rejects_duplicate_semantic_window(tmp_path) -> None:
    payload = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(payload["applications"][0])
    duplicate["id"] = "duplicate-id-with-same-meaning"
    payload["applications"].append(duplicate)
    applications_path = tmp_path / "applications.json"
    predictions_path = tmp_path / "predictions.json"
    applications_path.write_text(json.dumps(payload), encoding="utf-8")
    generate_predictions(predictions_path, applications_path)

    errors, _ = validate_data(
        applications_path=applications_path,
        predictions_path=predictions_path,
    )
    assert any("duplicate semantic application window" in error for error in errors)


def test_validation_rejects_unknown_applicant_category(tmp_path) -> None:
    payload = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    payload["applications"][0]["applicantCategories"] = ["overseas-student"]
    applications_path = tmp_path / "applications.json"
    predictions_path = tmp_path / "predictions.json"
    applications_path.write_text(json.dumps(payload), encoding="utf-8")
    generate_predictions(predictions_path, applications_path)

    errors, _ = validate_data(
        applications_path=applications_path,
        predictions_path=predictions_path,
    )
    assert any("unknown applicant categories" in error for error in errors)


def test_validation_rejects_orphan_programme_group_scope(tmp_path) -> None:
    payload = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    payload["applications"][0]["scopeType"] = "programme-group"
    payload["applications"][0]["scopeId"] = "missing-programme-group"
    applications_path = tmp_path / "applications.json"
    predictions_path = tmp_path / "predictions.json"
    applications_path.write_text(json.dumps(payload), encoding="utf-8")
    generate_predictions(predictions_path, applications_path)

    errors, _ = validate_data(
        applications_path=applications_path,
        predictions_path=predictions_path,
    )
    assert any(
        "programme-group scope references an unknown group" in error for error in errors
    )
