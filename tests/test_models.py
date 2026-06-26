from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from gradwindow.models import ApplicationWindow, EvidenceSnapshot, IntakeDetails, University
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


def test_intake_model_allows_same_year_and_two_year_academic_ranges() -> None:
    same_year = IntakeDetails.model_validate(
        {
            "label": "Calendar 2027",
            "cycleYear": 2027,
            "academicYearEnd": 2027,
            "term": "other",
            "startMonth": 1,
        }
    )
    two_year = IntakeDetails.model_validate(
        {
            "label": "2027/29",
            "cycleYear": 2027,
            "academicYearEnd": 2029,
            "term": "other",
            "startMonth": None,
        }
    )
    assert same_year.academic_year_end == 2027
    assert two_year.academic_year_end == 2029


def test_university_model_does_not_treat_qs_rank_as_list_position() -> None:
    payload = json.loads(
        (APPLICATIONS_PATH.parent / "universities.json").read_text(encoding="utf-8")
    )
    record = copy.deepcopy(payload["universities"][0])
    record["qsRank"] = 225
    parsed = University.model_validate(record)
    assert parsed.qs_rank == 225


def test_qs_universities_have_chinese_names_for_search() -> None:
    payload = json.loads(
        (APPLICATIONS_PATH.parent / "universities.json").read_text(encoding="utf-8")
    )
    missing = [
        university["id"]
        for university in payload["universities"]
        if not university.get("schoolZh")
    ]
    assert missing == []

    aliases_by_id = {
        university["id"]: university.get("schoolAliasesZh", [])
        for university in payload["universities"]
    }
    assert "港大" in aliases_by_id["the-university-of-hong-kong"]
    assert "宾大" in aliases_by_id["university-of-pennsylvania"]
    assert "曼大" in aliases_by_id["the-university-of-manchester"]


def test_global_rankings_have_chinese_names_for_search() -> None:
    payload = json.loads(
        (APPLICATIONS_PATH.parent / "global-rankings.json").read_text(
            encoding="utf-8"
        )
    )
    missing = []
    for ranking_id, ranking in payload["rankings"].items():
        missing.extend(
            f"{ranking_id}:{row['school']}"
            for row in ranking.get("rows", [])
            if not row.get("schoolZh")
        )
    assert missing == []
