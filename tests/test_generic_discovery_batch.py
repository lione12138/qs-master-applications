from __future__ import annotations

import json

import gradwindow.generic_discovery_batch as generic_discovery_batch
from gradwindow.generic_discovery_batch import (
    classify_generic_candidates,
    refresh_generic_discovery_report,
    run_assisted_discovery_entry,
    run_generic_discovery_batch,
)


def test_assisted_entry_passes_configured_search_priority(monkeypatch) -> None:
    captured = {}

    def fake_run(config, **_kwargs):
        captured["config"] = config
        return {"status": "no-results"}

    monkeypatch.setattr(
        generic_discovery_batch,
        "run_assisted_discovery",
        fake_run,
    )

    run_assisted_discovery_entry(
        {
            "universityId": "example-university",
            "seedUrls": ["https://example.edu/postgraduate"],
            "officialDomains": ["example.edu"],
            "assistedDiscovery": {
                "enabled": True,
                "maxResults": 12,
                "searchPriority": "high",
            },
        },
        {
            "school": "Example University",
            "admissionsUrl": "https://example.edu/postgraduate",
        },
        dry_run=True,
    )

    assert captured["config"].search_priority == "high"


def test_batch_skips_fallback_when_dedicated_discovery_succeeded(
    monkeypatch,
    tmp_path,
) -> None:
    config_path = tmp_path / "config.json"
    universities_path = tmp_path / "universities.json"
    candidates_path = tmp_path / "candidates.json"
    report_path = tmp_path / "report.json"
    config_path.write_text(
        json.dumps(
            {
                "schools": [
                    {
                        "name": "dedicated-fallback",
                        "universityId": "dedicated-university",
                        "enabled": True,
                        "discoveryRole": "fallback",
                        "seedUrls": ["https://dedicated.example/programmes"],
                    },
                    {
                        "name": "generic-primary",
                        "universityId": "generic-university",
                        "enabled": True,
                        "seedUrls": ["https://generic.example/programmes"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    universities_path.write_text(
        json.dumps(
            {
                "universities": [
                    {
                        "id": "dedicated-university",
                        "officialDomains": ["dedicated.example"],
                    },
                    {
                        "id": "generic-university",
                        "officialDomains": ["generic.example"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    candidates_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    discovered = []

    def fake_discover(adapter, **_kwargs):
        discovered.append(adapter.university_id)
        return {"status": "ok", "universityId": adapter.university_id}

    monkeypatch.setattr(generic_discovery_batch, "UNIVERSITIES_PATH", universities_path)
    monkeypatch.setattr(generic_discovery_batch, "discover_programmes", fake_discover)

    report = run_generic_discovery_batch(
        config_path=config_path,
        report_path=report_path,
        candidates_path=candidates_path,
        dry_run=True,
        successful_dedicated_university_ids={"dedicated-university"},
    )

    assert discovered == ["generic-university"]
    assert report["summary"]["schoolsSkippedByDedicated"] == 1
    assert report["results"][0]["batchStatus"] == "skipped"
    assert report["results"][0]["skipReason"] == "dedicated-primary-succeeded"


def test_classify_generic_candidates_splits_review_buckets() -> None:
    candidates = [
        {
            "id": "new-programme:ready",
            "status": "pending",
            "universityId": "example-university",
            "programme": {"name": "MSc Ready"},
            "windows": [
                {
                    "opensAt": "2026-09-01",
                    "opensAtBasis": "official",
                    "closesAt": "2027-01-14",
                }
            ],
            "parseStatus": "parsed",
            "reviewReason": "Review the automatically discovered programme.",
        },
        {
            "id": "new-programme:adapter",
            "status": "pending",
            "universityId": "example-university",
            "programme": {"name": "MSc Needs Adapter"},
            "windows": [{"opensAt": "2026-09-01", "closesAt": None}],
            "parseStatus": "incomplete",
            "reviewReason": "The page structure needs a school-specific parser.",
        },
        {
            "id": "new-programme:coming-soon",
            "status": "pending",
            "universityId": "example-university",
            "programme": {"name": "MSc Coming Soon"},
            "windows": [],
            "parseStatus": "no-deadline",
            "reviewReason": "No application deadline was parsed.",
            "evidenceExcerpt": "Applications will open soon.",
        },
        {
            "id": "new-programme:opening-date",
            "status": "pending",
            "universityId": "example-university",
            "programme": {"name": "MSc Deadline Only"},
            "windows": [{"opensAt": None, "closesAt": "2027-01-14"}],
            "parseStatus": "incomplete",
            "reviewReason": "At least one opening date is not published.",
        },
        {
            "id": "new-programme:deadline-unavailable",
            "status": "pending",
            "universityId": "example-university",
            "programme": {"name": "MSc Active No Deadline"},
            "windows": [],
            "parseStatus": "no-deadline",
            "reviewReason": "No application deadline was parsed.",
            "evidenceExcerpt": "You can still apply for 2026-27 entry.",
        },
        {
            "id": "new-programme:ignored",
            "status": "pending",
            "universityId": "other-university",
            "programme": {"name": "MSc Ignored"},
            "windows": [],
            "parseStatus": "no-deadline",
        },
    ]

    buckets = classify_generic_candidates(candidates, {"example-university"})

    assert [item["id"] for item in buckets["readyToApprove"]] == ["new-programme:ready"]
    assert [item["id"] for item in buckets["needsAdapter"]] == ["new-programme:adapter"]
    assert [item["id"] for item in buckets["needsOpeningDate"]] == [
        "new-programme:opening-date"
    ]
    assert [item["id"] for item in buckets["comingSoonMonitor"]] == [
        "new-programme:coming-soon"
    ]
    assert [item["id"] for item in buckets["deadlineUnavailableMonitor"]] == [
        "new-programme:deadline-unavailable"
    ]


def test_inferred_opening_dates_still_require_review() -> None:
    candidates = [
        {
            "id": "new-programme:inferred",
            "status": "pending",
            "universityId": "example-university",
            "programme": {"name": "MSc Inferred"},
            "windows": [
                {
                    "opensAt": "2025-09-01",
                    "opensAtBasis": "inferred-month-default",
                    "closesAt": "2026-08-13",
                }
            ],
            "parseStatus": "parsed",
            "reviewReason": "Opening date uses a configured cycle default.",
        }
    ]

    buckets = classify_generic_candidates(candidates, {"example-university"})

    assert buckets["readyToApprove"] == []
    assert [item["id"] for item in buckets["needsOpeningReview"]] == [
        "new-programme:inferred"
    ]
    assert buckets["needsAdapter"] == []


def test_configured_no_deadline_schools_are_monitored() -> None:
    candidates = [
        {
            "id": "new-programme:no-deadline",
            "status": "pending",
            "universityId": "example-university",
            "programme": {"name": "MSc No Deadline"},
            "windows": [],
            "parseStatus": "no-deadline",
            "reviewReason": "No application deadline was parsed.",
            "evidenceExcerpt": "The generic scraper did not capture a useful excerpt.",
        }
    ]

    buckets = classify_generic_candidates(
        candidates,
        {"example-university"},
        deadline_unavailable_university_ids={"example-university"},
    )

    assert [item["id"] for item in buckets["deadlineUnavailableMonitor"]] == [
        "new-programme:no-deadline"
    ]
    assert buckets["needsAdapter"] == []


def test_refresh_report_reclassifies_current_pending_candidates(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    candidates_path = tmp_path / "candidates.json"
    report_path = tmp_path / "report.json"
    config_path.write_text(
        json.dumps(
            {
                "schools": [
                    {
                        "universityId": "example-university",
                        "enabled": True,
                        "noDeadlineHandling": "monitor",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    candidates_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "new-programme:already-approved",
                        "status": "approved",
                        "universityId": "example-university",
                        "programme": {"name": "MSc Approved"},
                        "windows": [],
                        "parseStatus": "parsed",
                    },
                    {
                        "id": "new-programme:monitor",
                        "status": "pending",
                        "universityId": "example-university",
                        "programme": {"name": "MSc Monitor"},
                        "windows": [],
                        "parseStatus": "no-deadline",
                        "reviewReason": "No application deadline was parsed.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "meta": {"updatedAt": "stale"},
                "summary": {"readyToApprove": 19},
                "results": [{"universityId": "example-university"}],
                "classification": {"readyToApprove": [{"id": "stale"}]},
            }
        ),
        encoding="utf-8",
    )

    report = refresh_generic_discovery_report(
        config_path=config_path,
        report_path=report_path,
        candidates_path=candidates_path,
    )

    assert report["summary"]["readyToApprove"] == 0
    assert report["summary"]["deadlineUnavailableMonitor"] == 1
    assert report["classification"]["readyToApprove"] == []
    assert report["results"] == [{"universityId": "example-university"}]
    assert report["meta"]["classificationRefreshedFromCandidates"] is True
