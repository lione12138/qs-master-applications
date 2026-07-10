from __future__ import annotations

import json

from gradwindow import cli


class FakeAdapter:
    university_id = "example-university"
    catalog_url = "https://example.edu/programmes"


def test_pipeline_discovery_report_returns_success_payload(monkeypatch) -> None:
    def fake_discover(adapter):
        assert isinstance(adapter, FakeAdapter)
        return {"status": "ok", "catalogProgrammes": 3}

    monkeypatch.setattr(cli, "discover_programmes", fake_discover)

    report = cli._pipeline_discovery_report("example", FakeAdapter)

    assert report == {"status": "ok", "catalogProgrammes": 3}


def test_pipeline_discovery_report_converts_adapter_failure(monkeypatch) -> None:
    def fake_discover(_adapter):
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr(cli, "discover_programmes", fake_discover)

    report = cli._pipeline_discovery_report("example", FakeAdapter)

    assert report == {
        "status": "error",
        "adapter": "example",
        "universityId": "example-university",
        "sourceUrl": "https://example.edu/programmes",
        "errorType": "RuntimeError",
        "message": "HTTP 403",
    }


def test_approve_all_programmes_uses_all_pending_candidate_universities(
    monkeypatch,
    tmp_path,
) -> None:
    approved = []
    candidates_path = tmp_path / "programme-candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "new-programme:a",
                        "type": "new-programme",
                        "status": "pending",
                        "universityId": "generic-university",
                    },
                    {
                        "id": "new-programme:b",
                        "type": "new-programme",
                        "status": "approved",
                        "universityId": "already-approved-university",
                    },
                    {
                        "id": "other:c",
                        "type": "other",
                        "status": "pending",
                        "universityId": "other-university",
                    },
                    {
                        "id": "new-programme:d",
                        "type": "new-programme",
                        "status": "pending",
                        "universityId": "adapter-university",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "PROGRAMME_CANDIDATES_PATH", candidates_path)

    def fake_approve_programme_candidates(*, university_id, reviewer, parsed_only):
        approved.append((university_id, reviewer, parsed_only))
        return {"promotedProgrammes": 1, "promotedWindows": 2}

    monkeypatch.setattr(
        cli,
        "approve_programme_candidates",
        fake_approve_programme_candidates,
    )

    report = cli._approve_all_programmes(reviewer="codex", parsed_only=False)

    assert approved == [
        ("adapter-university", "codex", False),
        ("generic-university", "codex", False),
    ]
    assert report == {
        "adapter-university": {"promotedProgrammes": 1, "promotedWindows": 2},
        "generic-university": {"promotedProgrammes": 1, "promotedWindows": 2},
    }
