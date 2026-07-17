from __future__ import annotations

from gradwindow import cli
from gradwindow.candidate_review import attach_programme_candidate_evidence_hash
from gradwindow.io import write_json


class FakeAdapter:
    university_id = "example-university"
    catalog_url = "https://example.edu/programmes"


def test_pipeline_discovery_report_returns_success_payload(monkeypatch) -> None:
    def fake_discover(adapter, *, dry_run=False):
        assert isinstance(adapter, FakeAdapter)
        assert dry_run is False
        return {"status": "ok", "catalogProgrammes": 3}

    monkeypatch.setattr(cli, "discover_programmes", fake_discover)

    report = cli._pipeline_discovery_report("example", FakeAdapter)

    assert report == {"status": "ok", "catalogProgrammes": 3}


def test_pipeline_discovery_report_converts_adapter_failure(monkeypatch) -> None:
    def fake_discover(_adapter, *, dry_run=False):
        assert dry_run is True
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr(cli, "discover_programmes", fake_discover)

    report = cli._pipeline_discovery_report("example", FakeAdapter, dry_run=True)

    assert report == {
        "status": "error",
        "adapter": "example",
        "universityId": "example-university",
        "sourceUrl": "https://example.edu/programmes",
        "errorType": "RuntimeError",
        "message": "HTTP 403",
        "dryRun": True,
    }


def test_run_dedicated_discovery_returns_only_successful_university_ids(
    monkeypatch,
) -> None:
    class FirstAdapter:
        university_id = "first-university"

    class SecondAdapter:
        university_id = "second-university"

    monkeypatch.setattr(
        cli,
        "PROGRAMME_ADAPTERS",
        {"first": FirstAdapter, "second": SecondAdapter},
    )
    monkeypatch.setattr(
        cli,
        "_pipeline_discovery_report",
        lambda name, _factory, dry_run=False: {
            "status": "ok" if name == "first" else "error",
            "universityId": f"{name}-university",
            "dryRun": dry_run,
        },
    )

    reports, successful_ids = cli._run_dedicated_discovery(dry_run=True)

    assert [report["status"] for report in reports] == ["ok", "error"]
    assert successful_ids == {"first-university"}


def test_programme_candidate_hash_returns_one_locked_candidate(
    monkeypatch, tmp_path
) -> None:
    candidates_path = tmp_path / "programme-candidates.json"
    candidate = attach_programme_candidate_evidence_hash(
        {
            "id": "new-programme:a",
            "type": "new-programme",
            "status": "pending",
            "universityId": "generic-university",
        }
    )
    write_json(candidates_path, {"items": [candidate]})
    monkeypatch.setattr(cli, "PROGRAMME_CANDIDATES_PATH", candidates_path)

    report = cli._programme_candidate_hash(candidate["id"])

    assert report["candidateId"] == candidate["id"]
    assert report["evidenceHash"] == candidate["evidenceHash"]
    assert report["contentMatchesHash"] is True
