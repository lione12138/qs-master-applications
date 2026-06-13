from __future__ import annotations

import json

from gradwindow.review import generate_review_outputs


def test_review_queue_contains_confirmed_changes(tmp_path) -> None:
    monitor_path = tmp_path / "monitor.json"
    universities_path = tmp_path / "universities.json"
    queue_path = tmp_path / "queue.json"
    reports_dir = tmp_path / "reports"
    universities_path.write_text(
        json.dumps(
            {
                "universities": [
                    {
                        "id": "example",
                        "school": "Example University",
                        "qsRank": 12,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monitor_path.write_text(
        json.dumps(
            {
                "meta": {
                    "summary": {
                        "total": 1,
                        "ok": 1,
                        "blocked": 0,
                        "errors": 0,
                        "changed": 1,
                    }
                },
                "universities": {
                    "example": {
                        "url": "https://example.edu/graduate",
                        "status": "ok",
                        "changed": True,
                        "contentHash": "abcdef1234567890",
                        "checkedAt": "2026-06-14T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    report, summary = generate_review_outputs(
        monitor_path, universities_path, queue_path, reports_dir
    )
    assert report.exists()
    assert summary["confirmedChanges"] == 1
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue["items"][0]["type"] == "content-change"


def test_resolved_monitor_errors_leave_the_queue(tmp_path) -> None:
    monitor_path = tmp_path / "monitor.json"
    universities_path = tmp_path / "universities.json"
    queue_path = tmp_path / "queue.json"
    reports_dir = tmp_path / "reports"
    universities_path.write_text(
        json.dumps(
            {
                "universities": [
                    {
                        "id": "example",
                        "school": "Example University",
                        "qsRank": 12,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    queue_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "monitor-error:example",
                        "type": "monitor-error",
                        "universityId": "example",
                        "status": "pending",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monitor_path.write_text(
        json.dumps(
            {
                "meta": {
                    "summary": {
                        "total": 1,
                        "ok": 1,
                        "blocked": 0,
                        "errors": 0,
                        "changed": 0,
                    }
                },
                "universities": {
                    "example": {
                        "url": "https://example.edu/graduate",
                        "status": "ok",
                        "changed": False,
                        "checkedAt": "2026-06-14T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _, summary = generate_review_outputs(
        monitor_path, universities_path, queue_path, reports_dir
    )
    assert summary["pendingReview"] == 0
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue["items"] == []


def test_published_window_source_changes_enter_review_queue(tmp_path) -> None:
    monitor_path = tmp_path / "monitor.json"
    universities_path = tmp_path / "universities.json"
    applications_path = tmp_path / "applications.json"
    source_state_path = tmp_path / "source-state.json"
    queue_path = tmp_path / "queue.json"
    reports_dir = tmp_path / "reports"
    universities_path.write_text(
        json.dumps(
            {
                "universities": [
                    {
                        "id": "example",
                        "school": "Example University",
                        "qsRank": 9,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    applications_path.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "id": "window-1",
                        "universityId": "example",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monitor_path.write_text(
        json.dumps(
            {
                "meta": {
                    "summary": {
                        "total": 1,
                        "ok": 1,
                        "blocked": 0,
                        "errors": 0,
                        "changed": 0,
                    }
                },
                "universities": {
                    "example": {
                        "url": "https://example.edu/admissions",
                        "status": "ok",
                        "changed": False,
                        "checkedAt": "2026-06-14T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    source_state_path.write_text(
        json.dumps(
            {
                "applications": {
                    "window-1": {
                        "url": "https://example.edu/window",
                        "status": "ok",
                        "changed": True,
                        "contentHash": "abcdef1234567890",
                        "checkedAt": "2026-06-14T00:00:00Z",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    _, summary = generate_review_outputs(
        monitor_path,
        universities_path,
        queue_path,
        reports_dir,
        source_state_path,
        applications_path,
    )
    assert summary["windowSourceChanges"] == 1
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue["items"][0]["type"] == "window-source-change"
