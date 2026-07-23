from __future__ import annotations

import pytest

from gradwindow.programme_adapters.ubc import (
    CATALOG_URL,
    UBCAdapter,
)

CATALOG_HTML = """
<table class="views-table"><tbody>
  <tr><td>Computer Science</td><td><a href="/prospective-students/graduate-degree-programs/master-of-science-computer-science">Master of Science in Computer Science (MSc)</a></td><td>Faculty of Science</td></tr>
  <tr><td>Human Nutrition</td><td><a href="/prospective-students/graduate-degree-programs/master-of-science-human-nutrition">Master of Science in Human Nutrition (MSc)</a></td><td>Faculty of Land and Food Systems</td></tr>
  <tr><td>Education</td><td><a href="/prospective-students/graduate-degree-programs/master-of-education-example">Master of Education in Example (MEd)</a></td><td>Faculty of Education</td></tr>
</tbody></table>
"""

HUMAN_NUTRITION_HTML = """
<div class="view-gps-sits-ipo">
  May 2027 Intake Application Open Date 15 July 2026
  Canadian Applicants Application Deadline 1 September 2026
  Transcript Deadline 1 September 2026 Referee Deadline 15 September 2026
  International Applicants Application Deadline 1 September 2026
  Transcript Deadline 1 September 2026 Referee Deadline 15 September 2026
  September 2027 Intake Application Open Date 15 September 2026
  Canadian Applicants Application Deadline 1 February 2027
  International Applicants Application Deadline 15 January 2027
</div>
"""

EMPTY_DEADLINE_HTML = """
<div class="view-gps-sits-ipo"><div class="view-empty">
  Application open dates and deadlines for an upcoming intake have not yet
  been configured in the admissions system. Please check back later.
</div></div>
"""


def _fetcher(url: str) -> str:
    if url == f"{CATALOG_URL}?lev=Master%27s&page=0":
        return CATALOG_HTML
    if url == f"{CATALOG_URL}?lev=Master%27s&page=1":
        return "<html></html>"
    if url.endswith("master-of-science-human-nutrition"):
        return HUMAN_NUTRITION_HTML
    if url.endswith("master-of-science-computer-science"):
        return "<main><p>Programme-specific admissions information.</p></main>"
    return EMPTY_DEADLINE_HTML


def test_ubc_adapter_discovers_paginated_master_catalogue() -> None:
    catalog = UBCAdapter(
        minimum_expected_programmes=3,
        maximum_expected_programmes=4,
        detail_workers=1,
    ).parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {item.degree_type for item in catalog.programmes} == {"MSc", "MEd"}
    assert {item.faculty for item in catalog.programmes} == {
        "Faculty of Science",
        "Faculty of Land and Food Systems",
        "Faculty of Education",
    }


def test_ubc_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = UBCAdapter(
        minimum_expected_programmes=3, detail_workers=1
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if "Computer Science" in item.name
    )

    assert programme.id == "ubc-computer-science-msc"


def test_ubc_adapter_parses_equal_and_distinct_applicant_deadlines() -> None:
    catalog = UBCAdapter(
        minimum_expected_programmes=3, detail_workers=1
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if "Human Nutrition" in item.name
    )

    assert programme.parse_status == "parsed"
    assert len(programme.windows) == 3
    may_window = next(
        window for window in programme.windows if window.intake == "May 2027"
    )
    assert may_window.applicant_categories == ["all"]
    assert may_window.opens_at == "2026-07-15"
    assert may_window.closes_at == "2026-09-01"
    september_windows = [
        window for window in programme.windows if window.intake == "September 2027"
    ]
    assert {window.applicant_categories[0] for window in september_windows} == {
        "domestic-students",
        "international-students",
    }
    assert {window.closes_at for window in september_windows} == {
        "2027-02-01",
        "2027-01-15",
    }


def test_ubc_adapter_does_not_create_windows_without_an_exact_pair() -> None:
    catalog = UBCAdapter(
        minimum_expected_programmes=3, detail_workers=1
    ).parse_catalog_from_fetcher(_fetcher)
    unavailable = [
        item for item in catalog.programmes if "Human Nutrition" not in item.name
    ]

    assert all(item.windows == [] for item in unavailable)
    assert all(item.parse_status == "no-deadline" for item in unavailable)


def test_ubc_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        UBCAdapter(
            minimum_expected_programmes=4, detail_workers=1
        ).parse_catalog_from_fetcher(_fetcher)
