from __future__ import annotations

import json

import pytest

from gradwindow.approvals import approve_programme_candidates, approve_window
from gradwindow.paths import APPLICATIONS_PATH, PROGRAMS_PATH


def test_approve_window_promotes_valid_candidate(tmp_path) -> None:
    applications_path = tmp_path / "applications.json"
    candidates_path = tmp_path / "candidates.json"
    applications_path.write_text(
        APPLICATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    candidate_record = {
        "id": "eth-example-2027",
        "universityId": "eth-zurich-swiss-federal-institute-of-technology",
        "scopeType": "institution",
        "scopeId": "eth-zurich-swiss-federal-institute-of-technology",
        "intake": "2027 Fall",
        "round": "",
        "applicantCategories": ["all"],
        "opensAt": "2026-09-01",
        "closesAt": "2026-12-01",
        "applicationUrl": "https://ethz.ch/en/studies/master/application.html",
        "sourceUrl": "https://ethz.ch/en/studies/master/application/dates.html",
        "verifiedAt": "2026-06-14",
        "evidence": "Fixture with explicit dates for approval workflow testing.",
    }
    candidates_path.write_text(
        json.dumps(
            {
                "meta": {},
                "items": [
                    {
                        "id": "candidate-1",
                        "status": "pending",
                        "record": candidate_record,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    approved = approve_window(
        "candidate-1",
        "test-reviewer",
        candidates_path,
        applications_path,
    )
    assert approved["id"] == "eth-example-2027"
    applications = json.loads(applications_path.read_text(encoding="utf-8"))
    assert any(
        item["id"] == "eth-example-2027" for item in applications["applications"]
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    assert candidates["items"][0]["status"] == "approved"
    assert candidates["items"][0]["reviewedBy"] == "test-reviewer"


def test_approve_window_rejects_unknown_candidate(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text('{"items": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown candidate"):
        approve_window(
            "missing",
            "test-reviewer",
            candidates_path,
            APPLICATIONS_PATH,
        )


def test_parser_candidate_gets_fresh_review_evidence(tmp_path) -> None:
    applications_path = tmp_path / "applications.json"
    candidates_path = tmp_path / "candidates.json"
    applications_path.write_text(
        APPLICATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    applications = json.loads(applications_path.read_text(encoding="utf-8"))
    record = next(
        item
        for item in applications["applications"]
        if item["id"] == "eth-autumn-2026-swiss-bachelors"
    )
    proposed = {**record, "closesAt": "2026-05-01"}
    candidates_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "parser-candidate",
                        "type": "parser-date-change",
                        "status": "pending",
                        "record": proposed,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    approved = approve_window(
        "parser-candidate",
        "test-reviewer",
        candidates_path,
        applications_path,
    )
    assert "test-reviewer reviewed the official source" in approved["evidence"]
    assert "2026-04-01 to 2026-05-01" in approved["evidence"]


def test_approve_programme_candidates_promotes_parsed_windows(tmp_path) -> None:
    programs_path = tmp_path / "programs.json"
    applications_path = tmp_path / "applications.json"
    candidates_path = tmp_path / "programme-candidates.json"
    programs_path.write_text(PROGRAMS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    applications_path.write_text(
        APPLICATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    candidate = {
        "id": "new-programme:imperial-example-msc",
        "type": "new-programme",
        "status": "pending",
        "universityId": "imperial-college-london",
        "programme": {
            "id": "imperial-example-msc",
            "universityId": "imperial-college-london",
            "name": "MSc Example",
            "degreeType": "MSc",
            "faculty": "Department A | Department A",
            "applicationUrl": "https://myimperial.powerappsportals.com/",
            "sourceUrl": (
                "https://www.imperial.ac.uk/study/courses/"
                "postgraduate-taught/2026/example/"
            ),
        },
        "windows": [
            {
                "intake": "September 2026",
                "round": "Round 2",
                "applicantCategories": ["all"],
                "opensAt": "2025-09-29",
                "closesAt": "2026-01-07",
            }
        ],
        "parseStatus": "parsed",
    }
    candidates_path.write_text(
        json.dumps({"meta": {}, "items": [candidate]}),
        encoding="utf-8",
    )

    report = approve_programme_candidates(
        university_id="imperial-college-london",
        reviewer="test-reviewer",
        candidates_path=candidates_path,
        programs_path=programs_path,
        applications_path=applications_path,
    )

    assert report["promotedProgrammes"] == 1
    assert report["promotedWindows"] == 1
    programs = json.loads(programs_path.read_text(encoding="utf-8"))["programs"]
    programme = next(item for item in programs if item["id"] == "imperial-example-msc")
    assert programme["faculty"] == "Department A"
    applications = json.loads(applications_path.read_text(encoding="utf-8"))[
        "applications"
    ]
    window = next(
        item
        for item in applications
        if item["id"] == "imperial-example-msc-2026-round-2"
    )
    assert window["scopeType"] == "programme"
    assert window["scopeId"] == "imperial-example-msc"
    assert window["intakeDetails"]["cycleYear"] == 2026
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["items"]
    assert candidates[0]["status"] == "approved"
