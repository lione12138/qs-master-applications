from __future__ import annotations

import importlib.util
import json
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest


def load_module():
    path = Path(__file__).parents[1] / "scripts" / "notify_subscribers.py"
    spec = importlib.util.spec_from_file_location("notify_subscribers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_current_open_events_only_returns_official_open_windows() -> None:
    module = load_module()
    events = module.current_open_events(date(2026, 6, 15))
    ids = {event["id"] for event in events}
    assert "ucl-advanced-materials-science-2026-visa" in ids
    assert "um-coursework-postgraduate-october-2026" in ids
    assert "glasgow-computing-science-september-2026-round-6" in ids
    assert "kth-computer-science-autumn-2027" not in ids
    assert "snu-international-graduate-spring-2027" not in ids
    assert all(event["applicationUrl"].startswith("https://") for event in events)


def test_notify_http_error_is_reported(
    monkeypatch,
    capsys,
) -> None:
    module = load_module()
    monkeypatch.setenv("GRADWINDOW_SUBSCRIBE_URL", "https://notify.example")
    monkeypatch.setenv("GRADWINDOW_NOTIFY_API_KEY", "bad-key")

    def fake_urlopen(_request, timeout):
        assert timeout == 45
        raise HTTPError(
            "https://notify.example/admin/notify",
            401,
            "Unauthorized",
            {},
            BytesIO(b'{"ok":false}'),
        )

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    ok = module.notify(
        [
            {
                "id": "window-1",
                "school": "Example University",
                "program": "MSc Example",
                "opensAt": "2026-07-01",
                "closesAt": "2026-07-31",
                "applicationUrl": "https://example.edu/apply",
                "sourceUrl": "https://example.edu/source",
            }
        ]
    )

    assert ok is False
    assert "HTTP 401 Unauthorized" in capsys.readouterr().err


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_notify_reports_provider_delivery_failures(monkeypatch, capsys) -> None:
    module = load_module()
    monkeypatch.setenv("GRADWINDOW_SUBSCRIBE_URL", "https://notify.example")
    monkeypatch.setenv("GRADWINDOW_NOTIFY_API_KEY", "shared-key")
    monkeypatch.setattr(
        module,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse({"ok": True, "sent": 1, "failed": 1}),
    )

    ok = module.notify(
        [
            {
                "id": "window-1",
                "school": "Example University",
                "program": "MSc Example",
                "opensAt": "2026-07-01",
                "closesAt": "2026-07-31",
                "applicationUrl": "https://example.edu/apply",
                "sourceUrl": "https://example.edu/source",
            }
        ]
    )

    assert ok is False
    assert "1 deliveries failed" in capsys.readouterr().out


def test_main_exits_nonzero_when_notification_fails(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "current_open_events", lambda: [{"id": "window-1"}])
    monkeypatch.setattr(module, "notify", lambda _events: False)
    monkeypatch.setattr(module.sys, "argv", ["notify_subscribers.py"])

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 1


def test_notify_normalizes_bearer_api_key(monkeypatch) -> None:
    module = load_module()
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout=45):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        return FakeResponse({"ok": True, "sent": 1, "failed": 0})

    monkeypatch.setenv("GRADWINDOW_SUBSCRIBE_URL", " https://example.edu/ ")
    monkeypatch.setenv(
        "GRADWINDOW_NOTIFY_API_KEY", "  " + "Bearer " + "demo-token" + " \n"
    )
    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    assert module.notify([{"id": "example-window", "opensAt": "2026-07-10"}]) is True
    assert captured["url"] == "https://example.edu/admin/notify"
    assert captured["authorization"] == "Bearer " + "demo-token"
