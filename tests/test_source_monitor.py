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
    evidence = json.loads(
        (tmp_path / "evidence" / "one.json").read_text(encoding="utf-8")
    )
    assert evidence["excerpt"] == "Applications close 15 January 2027."
