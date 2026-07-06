from __future__ import annotations

import json

from gradwindow import source_monitor


def test_source_monitor_fetches_duplicate_urls_once(tmp_path, monkeypatch) -> None:
    applications_path = tmp_path / "applications.json"
    state_path = tmp_path / "state.json"
    applications_path.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "id": "one",
                        "universityId": "u",
                        "sourceUrl": "https://example.edu/deadlines",
                    },
                    {
                        "id": "two",
                        "universityId": "u",
                        "sourceUrl": "https://example.edu/deadlines",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_check(university, previous, capture_evidence=False):
        calls.append(university["homepageUrl"])
        return {
            "url": university["homepageUrl"],
            "checkedAt": "2026-06-14T00:00:00Z",
            "status": "ok",
            "changed": False,
            "contentHash": "abc",
            "evidenceExcerpt": "Applications close 15 January 2027.",
        }

    monkeypatch.setattr(source_monitor, "check_university", fake_check)
    summary = source_monitor.monitor_application_sources(
        applications_path, state_path, workers=2
    )
    assert calls == ["https://example.edu/deadlines"]
    assert summary["total"] == 2
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(state["applications"]) == {"one", "two"}
    assert state["meta"]["uniqueSourcePages"] == 1
    evidence_bundle = json.loads(
        (tmp_path / "evidence" / "u.json").read_text(encoding="utf-8")
    )
    evidence = evidence_bundle["snapshots"]["one"]
    assert evidence["excerpt"] == "Applications close 15 January 2027."


def test_source_monitor_preserves_better_existing_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    applications_path = tmp_path / "applications.json"
    state_path = tmp_path / "state.json"
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    applications_path.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "id": "dynamic-window",
                        "universityId": "u",
                        "sourceUrl": "https://example.edu/dynamic",
                        "opensAt": "2025-11-01",
                        "closesAt": "2026-03-31",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    existing_path = evidence_dir / "u.json"
    existing_path.write_text(
        json.dumps(
            {
                "universityId": "u",
                "snapshots": {
                    "dynamic-window": {"quality": "rendered"},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        source_monitor,
        "check_university",
        lambda *args, **kwargs: {
            "url": "https://example.edu/dynamic",
            "checkedAt": "2026-06-14T00:00:00Z",
            "status": "ok",
            "changed": False,
            "contentHash": "abc",
            "evidenceContext": {
                "excerpt": "Unrelated event on 5 September 2026.",
                "contentSelector": "body",
                "matchedTextBefore": "",
                "matchedText": "Unrelated event on 5 September 2026.",
                "matchedTextAfter": "",
            },
        },
    )
    source_monitor.monitor_application_sources(
        applications_path,
        state_path,
        evidence_dir=evidence_dir,
        workers=1,
    )
    evidence_bundle = json.loads(existing_path.read_text(encoding="utf-8"))
    assert evidence_bundle["snapshots"]["dynamic-window"] == {"quality": "rendered"}


def test_source_monitor_uses_matched_context_when_excerpt_misses_dates(
    tmp_path,
    monkeypatch,
) -> None:
    applications_path = tmp_path / "applications.json"
    state_path = tmp_path / "state.json"
    applications_path.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "id": "context-window",
                        "universityId": "u",
                        "sourceUrl": "https://example.edu/admissions",
                        "opensAt": "2025-09-03",
                        "closesAt": "2025-12-23",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        source_monitor,
        "check_university",
        lambda *args, **kwargs: {
            "url": "https://example.edu/admissions",
            "checkedAt": "2026-06-15T00:00:00Z",
            "status": "ok",
            "changed": False,
            "contentHash": "abc",
            "evidenceContext": {
                "excerpt": "",
                "contentSelector": "article",
                "matchedTextBefore": "Applications open for",
                "matchedText": (
                    "Fall admission from September 3, 2025 until December 23, 2025."
                ),
                "matchedTextAfter": "Admission is for fall quarter.",
            },
        },
    )

    source_monitor.monitor_application_sources(
        applications_path,
        state_path,
        workers=1,
    )

    evidence_bundle = json.loads(
        (tmp_path / "evidence" / "u.json").read_text(encoding="utf-8")
    )
    evidence = evidence_bundle["snapshots"]["context-window"]
    assert "September 3, 2025" in evidence["excerpt"]
    assert "December 23, 2025" in evidence["excerpt"]
