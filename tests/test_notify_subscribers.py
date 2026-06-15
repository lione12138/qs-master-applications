from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path


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
