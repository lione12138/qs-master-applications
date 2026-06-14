from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from gradwindow.models import ApplicationWindow, EvidenceSnapshot
from gradwindow.paths import APPLICATIONS_PATH, EVIDENCE_DIR


def test_application_model_accepts_current_record() -> None:
    record = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))[
        "applications"
    ][0]
    parsed = ApplicationWindow.model_validate(record)
    assert parsed.intake_details.cycle_year == 2026


def test_application_model_rejects_unknown_fields() -> None:
    record = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))[
        "applications"
    ][0]
    invalid = copy.deepcopy(record)
    invalid["unreviewedFlag"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ApplicationWindow.model_validate(invalid)


def test_application_model_rejects_path_like_id() -> None:
    record = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))[
        "applications"
    ][0]
    invalid = copy.deepcopy(record)
    invalid["id"] = "../outside"
    with pytest.raises(ValidationError, match="String should match pattern"):
        ApplicationWindow.model_validate(invalid)


def test_evidence_snapshot_accepts_current_record() -> None:
    snapshot_path = next(EVIDENCE_DIR.glob("*.json"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    parsed = EvidenceSnapshot.model_validate(snapshot)
    assert parsed.captured_at.tzinfo is not None
