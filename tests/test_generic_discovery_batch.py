from __future__ import annotations

from gradwindow.generic_discovery_batch import classify_generic_candidates


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
