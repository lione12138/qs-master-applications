from __future__ import annotations

import gradwindow.cli as cli


class _Adapter:
    university_id = "example-university"
    catalog_url = "https://example.edu/catalog"


def _adapter_factory() -> _Adapter:
    return _Adapter()


def test_pipeline_discovery_report_returns_success_payload(monkeypatch) -> None:
    expected = {"status": "ok", "universityId": "example-university"}
    monkeypatch.setattr(cli, "discover_programmes", lambda adapter: expected)

    report = cli._pipeline_discovery_report("example", _adapter_factory)

    assert report is expected


def test_pipeline_discovery_report_converts_adapter_failure_to_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "discover_programmes",
        lambda adapter: (_ for _ in ()).throw(ValueError("HTTP 403")),
    )

    report = cli._pipeline_discovery_report("example", _adapter_factory)

    assert report == {
        "status": "error",
        "adapter": "example",
        "universityId": "example-university",
        "sourceUrl": "https://example.edu/catalog",
        "errorType": "ValueError",
        "message": "HTTP 403",
        "dryRun": False,
    }
