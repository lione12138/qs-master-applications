from __future__ import annotations

import json

import pytest

from gradwindow.approvals import (
    approve_official_adapter_window_candidates,
    approve_programme_candidates,
    approve_window,
)
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
    programs_path.write_text(
        PROGRAMS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
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
                "opensAtBasis": "official",
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


def test_approve_programme_candidates_rejects_inferred_opening(tmp_path) -> None:
    programs_path = tmp_path / "programs.json"
    applications_path = tmp_path / "applications.json"
    candidates_path = tmp_path / "programme-candidates.json"
    programs_path.write_text(
        PROGRAMS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    applications_path.write_text(
        APPLICATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    candidates_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "new-programme:inferred-example",
                        "type": "new-programme",
                        "status": "pending",
                        "universityId": "imperial-college-london",
                        "programme": {
                            "id": "inferred-example",
                            "universityId": "imperial-college-london",
                            "name": "MSc Inferred Example",
                            "degreeType": "MSc",
                            "faculty": "",
                            "applicationUrl": "https://www.imperial.ac.uk/study/",
                            "sourceUrl": "https://www.imperial.ac.uk/study/",
                        },
                        "windows": [
                            {
                                "intake": "September 2027",
                                "round": "Main",
                                "applicantCategories": ["all"],
                                "opensAt": "2026-10-01",
                                "opensAtBasis": "inferred-cycle-default",
                                "closesAt": "2027-01-01",
                            }
                        ],
                        "parseStatus": "parsed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = approve_programme_candidates(
        university_id="imperial-college-london",
        reviewer="test-reviewer",
        candidates_path=candidates_path,
        programs_path=programs_path,
        applications_path=applications_path,
    )

    assert report["promotedProgrammes"] == 0
    assert report["promotedWindows"] == 0
    assert report["remainingPending"] == 1


def test_approve_programme_candidates_can_publish_catalogue_only_records(
    tmp_path,
) -> None:
    programs_path = tmp_path / "programs.json"
    applications_path = tmp_path / "applications.json"
    candidates_path = tmp_path / "programme-candidates.json"
    programs_path.write_text(
        PROGRAMS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    applications_path.write_text(
        APPLICATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    candidate = {
        "id": "new-programme:catalogue-only-example",
        "type": "new-programme",
        "status": "pending",
        "universityId": "imperial-college-london",
        "programme": {
            "id": "catalogue-only-example",
            "universityId": "imperial-college-london",
            "name": "MSc Catalogue Only Example",
            "degreeType": "MSc",
            "faculty": "Department A",
            "applicationUrl": "https://www.imperial.ac.uk/study/",
            "sourceUrl": "https://www.imperial.ac.uk/study/courses/",
        },
        "windows": [],
        "parseStatus": "no-deadline",
    }
    candidates_path.write_text(
        json.dumps({"meta": {}, "items": [candidate]}), encoding="utf-8"
    )

    report = approve_programme_candidates(
        university_id="imperial-college-london",
        reviewer="test-reviewer",
        parsed_only=False,
        candidates_path=candidates_path,
        programs_path=programs_path,
        applications_path=applications_path,
    )

    assert report == {
        "promotedProgrammes": 1,
        "promotedWindows": 0,
        "remainingPending": 0,
    }
    programs = json.loads(programs_path.read_text(encoding="utf-8"))["programs"]
    assert any(item["id"] == "catalogue-only-example" for item in programs)
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["items"]
    assert candidates[0]["status"] == "approved"


def test_approve_window_rejects_non_official_opening_basis(tmp_path) -> None:
    candidates_path = tmp_path / "window-candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "adapter-window:inferred",
                        "type": "adapter-new-window",
                        "status": "pending",
                        "openingBasis": "inferred-cycle-default",
                        "record": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="official opening date"):
        approve_window(
            "adapter-window:inferred",
            "test-reviewer",
            candidates_path,
            APPLICATIONS_PATH,
        )


def test_batch_approval_only_promotes_official_adapter_windows(tmp_path) -> None:
    applications_path = tmp_path / "applications.json"
    candidates_path = tmp_path / "window-candidates.json"
    applications_path.write_text(
        APPLICATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    base_record = {
        "universityId": "eth-zurich-swiss-federal-institute-of-technology",
        "scopeType": "institution",
        "scopeId": "eth-zurich-swiss-federal-institute-of-technology",
        "intake": "2027 Fall",
        "round": "Main",
        "applicantCategories": ["all"],
        "opensAt": "2026-09-01",
        "closesAt": "2026-12-01",
        "applicationUrl": "https://ethz.ch/en/studies/master/application.html",
        "sourceUrl": "https://ethz.ch/en/studies/master/application/dates.html",
        "verifiedAt": "2026-07-01",
        "evidence": "Official exact dates used by the batch approval test.",
    }
    candidates_path.write_text(
        json.dumps(
            {
                "meta": {},
                "items": [
                    {
                        "id": "official-adapter-window",
                        "type": "adapter-new-window",
                        "status": "pending",
                        "openingBasis": "official",
                        "record": {**base_record, "id": "batch-official-window"},
                    },
                    {
                        "id": "inferred-adapter-window",
                        "type": "adapter-new-window",
                        "status": "pending",
                        "openingBasis": "inferred-cycle-default",
                        "record": {**base_record, "id": "batch-inferred-window"},
                    },
                    {
                        "id": "parser-window",
                        "type": "parser-date-change",
                        "status": "pending",
                        "openingBasis": "official",
                        "record": {**base_record, "id": "batch-parser-window"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = approve_official_adapter_window_candidates(
        reviewer="automated-policy",
        university_ids={"eth-zurich-swiss-federal-institute-of-technology"},
        candidates_path=candidates_path,
        applications_path=applications_path,
    )

    assert report == {"promotedWindows": 1, "remainingPending": 1}
    applications = json.loads(applications_path.read_text(encoding="utf-8"))[
        "applications"
    ]
    assert any(item["id"] == "batch-official-window" for item in applications)
    assert not any(item["id"] == "batch-inferred-window" for item in applications)
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["items"]
    assert candidates[0]["status"] == "approved"
    assert candidates[0]["reviewedBy"] == "automated-policy"
    assert candidates[1]["status"] == "pending"
    assert candidates[2]["status"] == "pending"
