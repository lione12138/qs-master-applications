from __future__ import annotations

import json

import pytest

from gradwindow import deadlines
from gradwindow.deadlines import extract_iso_date


def test_extract_iso_date_from_named_group() -> None:
    html = "<div>Deadline: 2027-01-15</div>"
    assert (
        extract_iso_date(html, r"Deadline:\s*(?P<date>\d{4}-\d{2}-\d{2})")
        == "2027-01-15"
    )


def test_extract_iso_date_returns_none_without_match() -> None:
    assert (
        extract_iso_date("<div>No date</div>", r"(?P<date>\d{4}-\d{2}-\d{2})") is None
    )


def test_extract_iso_date_rejects_invalid_date() -> None:
    with pytest.raises(ValueError):
        extract_iso_date("<div>2027-19-99</div>", r"(?P<date>\d{4}-\d{2}-\d{2})")


def test_parser_change_creates_candidate_without_mutating_official_data(
    tmp_path, monkeypatch
) -> None:
    applications_path = tmp_path / "applications.json"
    sources_path = tmp_path / "sources.json"
    report_path = tmp_path / "report.json"
    candidates_path = tmp_path / "candidates.json"
    applications = {
        "meta": {"updatedAt": "2026-06-01T00:00:00Z"},
        "applications": [
            {
                "id": "window-1",
                "universityId": "example",
                "scopeType": "institution",
                "scopeId": "example",
                "intake": "Fall 2027",
                "round": "",
                "applicantCategories": ["all"],
                "opensAt": "2026-09-01",
                "closesAt": "2026-12-01",
                "applicationUrl": "https://example.edu/apply",
                "sourceUrl": "https://example.edu/deadlines",
                "verifiedAt": "2026-06-01",
                "evidence": "Previously verified fixture.",
            }
        ],
    }
    applications_path.write_text(json.dumps(applications), encoding="utf-8")
    sources_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "enabled": True,
                        "recordId": "window-1",
                        "url": "https://example.edu/deadlines",
                        "closeDateRegex": (r"Deadline:\s*(?P<date>\d{4}-\d{2}-\d{2})"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        deadlines,
        "fetch",
        lambda url: "<div>Deadline: 2026-12-15</div>",
    )

    report = deadlines.update_deadlines(
        applications_path=applications_path,
        sources_path=sources_path,
        report_path=report_path,
        candidates_path=candidates_path,
    )

    assert report["results"][0]["status"] == "candidate-created"
    assert json.loads(applications_path.read_text(encoding="utf-8")) == applications
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    assert candidates["items"][0]["record"]["closesAt"] == "2026-12-15"
    assert candidates["items"][0]["status"] == "pending"
