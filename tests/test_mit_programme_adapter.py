from __future__ import annotations

import pytest

from gradwindow.programme_adapters.mit import MITAdapter
from gradwindow.programme_discovery import discover_programmes


MIT_HTML = """
<html><body><table class="w-100">
  <thead><tr>
    <th>Program</th><th>Application Opens</th><th>Application Deadline</th>
  </tr></thead>
  <tbody>
    <tr><td><a href="https://oge.mit.edu/programs/architecture/">Architecture</a></td>
      <td>October 1</td><td>January 7</td></tr>
    <tr><td><a href="https://oge.mit.edu/programs/sloan-mba/">MIT Sloan MBA Program</a></td>
      <td>Summer</td><td>September 29, January 13, April 6</td></tr>
    <tr><td><a href="https://oge.mit.edu/programs/whoi/">MIT-WHOI Joint Program</a></td>
      <td>July 1, October 1</td><td>October 1, December 1</td></tr>
    <tr><td><a href="https://oge.mit.edu/programs/executive-mba/">MIT Sloan Executive MBA Program</a></td>
      <td>Summer</td><td>Multiple Rounds of Deadlines</td></tr>
  </tbody>
</table></body></html>
"""


def test_mit_adapter_extracts_cycle_dates_and_multiple_rounds() -> None:
    catalog = MITAdapter(
        minimum_expected_programmes=1,
        intake_year=2027,
    ).parse_catalog(MIT_HTML)

    architecture = next(item for item in catalog.programmes if "architecture" in item.id)
    assert architecture.application_url.endswith("/architecture/")
    assert [(item.opens_at, item.closes_at) for item in architecture.windows] == [
        ("2026-10-01", "2027-01-07")
    ]

    mba = next(item for item in catalog.programmes if item.name == "MIT Sloan MBA Program")
    assert mba.degree_type == "MBA"
    assert mba.parse_status == "incomplete"
    assert [item.round for item in mba.windows] == ["Round 1", "Round 2", "Round 3"]
    assert [item.closes_at for item in mba.windows] == [
        "2026-09-29",
        "2027-01-13",
        "2027-04-06",
    ]
    assert all(item.opens_at is None for item in mba.windows)

    whoi = next(item for item in catalog.programmes if "whoi" in item.id)
    assert [(item.opens_at, item.closes_at) for item in whoi.windows] == [
        ("2026-07-01", "2026-10-01"),
        ("2026-10-01", "2026-12-01"),
    ]

    executive = next(item for item in catalog.programmes if "executive" in item.id)
    assert executive.windows == []
    assert executive.parse_status == "no-deadline"


def test_mit_adapter_rejects_missing_or_implausibly_small_catalog() -> None:
    with pytest.raises(ValueError, match="table was not found"):
        MITAdapter(minimum_expected_programmes=1, intake_year=2027).parse_catalog(
            "<html></html>"
        )

    with pytest.raises(ValueError, match="catalog only contained"):
        MITAdapter(minimum_expected_programmes=25, intake_year=2027).parse_catalog(
        MIT_HTML
        )


def test_mit_discovery_keeps_inexact_openings_for_review(tmp_path) -> None:
    programs_path = tmp_path / "programs.json"
    candidates_path = tmp_path / "candidates.json"
    state_path = tmp_path / "state.json"
    programs_path.write_text('{"programs": []}', encoding="utf-8")

    report = discover_programmes(
        MITAdapter(minimum_expected_programmes=1, intake_year=2027),
        programs_path=programs_path,
        candidates_path=candidates_path,
        state_path=state_path,
        fetcher=lambda url: MIT_HTML,
    )

    assert report["catalogProgrammes"] == 4
    assert report["programmesWithoutDeadlines"] == 1
    assert report["programmesNeedingReview"] == 2
    import json

    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["items"]
    mba = next(item for item in candidates if item["programme"]["id"] == "mit-sloan-mba-program-masters")
    assert {window["intake"] for window in mba["windows"]} == {"September 2027"}
    assert all(window["opensAt"] is None for window in mba["windows"])
    assert "not published as an exact date" in mba["reviewReason"]
