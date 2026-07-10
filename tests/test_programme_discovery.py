from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.cuhk import CUHKAdapter
from gradwindow.programme_discovery import discover_programmes

CUHK_HTML = """
<html><body>
  <p>Application Commencement Date*: 1 September 2025 at 09:00 a.m.</p>
  <div class="view-grouping">
    <div class="view-grouping-header">Faculty of Engineering</div>
    <div class="view-grouping-content">
      <div class="collapse-item">
        <div class="collapse-item-header"><span>Computer Science and Engineering</span></div>
        <div class="collapse-item-content">
          <div class="col-12">
            <h3>Research Programmes</h3>
            <div class="MAinAnthropology my-4">
              <div class="title-bg">MPhil-PhD in Computer Science</div>
              <div class="content-bg"><p>Main Round: 1 December 2025</p></div>
            </div>
          </div>
          <div class="col-12">
            <h3>Taught Programmes</h3>
            <div class="MAinAnthropology my-4">
              <div class="title-bg">MSc in Computer Science</div>
              <div class="content-bg"><p>31 January 2026</p></div>
            </div>
            <div class="MAinAnthropology my-4">
              <div class="title-bg">MSc in Artificial Intelligence</div>
              <div class="content-bg">
                <p>1st round: 6 Oct 2025 (Mon)</p>
                <p>Final round: 26 Feb 2026 (Thurs)</p>
                <p>Applications submitted after 26 Feb 2026 may be considered.</p>
              </div>
            </div>
            <div class="MAinAnthropology my-4">
              <div class="title-bg">PgD in Financial Technology</div>
              <div class="content-bg"><p>Final round: 26 Feb 2026</p></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="view-grouping">
    <div class="view-grouping-header">Faculty of Business Administration</div>
    <div class="view-grouping-content">
      <div class="collapse-item">
        <div class="collapse-item-header"><span>Business Administration</span></div>
        <div class="collapse-item-content">
          <div class="col-12">
            <h3>Taught Programmes</h3>
            <div class="MAinAnthropology my-4">
              <div class="title-bg">Executive Master of Professional Accountancy</div>
              <div class="content-bg"><p>To be confirmed</p></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</body></html>
"""


def test_cuhk_adapter_extracts_only_masters_and_deadline_rounds() -> None:
    adapter = CUHKAdapter(minimum_expected_programmes=1)

    catalog = adapter.parse_catalog(CUHK_HTML)

    assert catalog.application_opens_at == "2025-09-01"
    assert [item.id for item in catalog.programmes] == [
        "cuhk-artificial-intelligence-msc",
        "cuhk-computer-science-msc",
        "cuhk-professional-accountancy-executive-master",
    ]
    ai = next(item for item in catalog.programmes if "artificial" in item.id)
    assert [(window.round, window.closes_at) for window in ai.windows] == [
        ("1st round", "2025-10-06"),
        ("Final round", "2026-02-26"),
    ]
    assert ai.faculty == "Faculty of Engineering"
    assert ai.department == "Computer Science and Engineering"
    accountancy = next(item for item in catalog.programmes if "accountancy" in item.id)
    assert accountancy.windows == []
    assert accountancy.parse_status == "no-deadline"


def test_cuhk_adapter_rejects_implausibly_small_catalog() -> None:
    adapter = CUHKAdapter(minimum_expected_programmes=10)

    with pytest.raises(ValueError, match="catalog only contained"):
        adapter.parse_catalog(CUHK_HTML)


def test_early_round_before_shared_commencement_requires_opening_review(
    tmp_path,
) -> None:
    html = CUHK_HTML.replace(
        "To be confirmed",
        "1 August 2025 (Early Round)",
    )
    adapter = CUHKAdapter(minimum_expected_programmes=1)
    programs_path = tmp_path / "programs.json"
    candidates_path = tmp_path / "candidates.json"
    state_path = tmp_path / "state.json"
    programs_path.write_text(json.dumps({"programs": []}), encoding="utf-8")

    discover_programmes(
        adapter,
        programs_path=programs_path,
        candidates_path=candidates_path,
        state_path=state_path,
        fetcher=lambda url: html,
    )

    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["items"]
    accountancy = next(
        item for item in candidates if "accountancy" in item["programme"]["id"]
    )
    assert accountancy["windows"] == [
        {
            "intake": "September 2026",
            "round": "Early round",
            "applicantCategories": ["all"],
            "opensAt": None,
            "opensAtBasis": "missing",
            "closesAt": "2025-08-01",
            "sourceUrl": "https://www.gs.cuhk.edu.hk/admissions/application-deadline",
        }
    ]
    assert "programme-specific opening date" in accountancy["reviewReason"]


def test_discovery_creates_candidates_without_mutating_programmes(
    tmp_path,
) -> None:
    programs_path = tmp_path / "programs.json"
    candidates_path = tmp_path / "programme-candidates.json"
    state_path = tmp_path / "programme-catalog-state.json"
    programs = {
        "programs": [
            {
                "id": "cuhk-computer-science-msc",
                "universityId": "the-chinese-university-of-hong-kong",
                "name": "MSc in Computer Science",
                "degreeType": "MSc",
                "faculty": "Computer Science and Engineering",
                "applicationUrl": "https://example.test/apply",
                "sourceUrl": "https://example.test/deadlines",
            }
        ]
    }
    programs_path.write_text(json.dumps(programs), encoding="utf-8")
    adapter = CUHKAdapter(minimum_expected_programmes=1)

    report = discover_programmes(
        adapter,
        programs_path=programs_path,
        candidates_path=candidates_path,
        state_path=state_path,
        fetcher=lambda url: CUHK_HTML,
    )

    assert report["status"] == "ok"
    assert report["catalogProgrammes"] == 3
    assert report["newCandidates"] == 2
    assert json.loads(programs_path.read_text(encoding="utf-8")) == programs
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["items"]
    assert [item["programme"]["id"] for item in candidates] == [
        "cuhk-artificial-intelligence-msc",
        "cuhk-professional-accountancy-executive-master",
    ]
    assert candidates[0]["windows"][0]["opensAt"] == "2025-09-01"
    assert candidates[1]["reviewReason"] == "No application deadline was parsed."
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["universities"][adapter.university_id]["itemCount"] == 3

    repeated = discover_programmes(
        adapter,
        programs_path=programs_path,
        candidates_path=candidates_path,
        state_path=state_path,
        fetcher=lambda url: CUHK_HTML,
    )

    assert repeated["newCandidates"] == 0
    assert repeated["pendingCandidates"] == 2
