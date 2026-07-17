from __future__ import annotations

import pytest

from gradwindow.programme_adapters.cmu import CATALOG_FETCH_URL, CMUAdapter

CATALOG_HTML = """
<main id="content">
  <h2 id="edition">2025-2026 Catalog</h2>
  <h2>College of Engineering</h2>
  <h4>Biomedical Engineering</h4>
  <ul>
    <li>M.S. in Biomedical Engineering</li>
    <li>Ph.D. in Biomedical Engineering</li>
  </ul>
  <h2>School of Computer Science</h2>
  <h4>Computer Science</h4>
  <ul>
    <li>M.S. in Computer Science</li>
    <li>M.S. in Computer Science - Research Thesis (5th Year Scholars Program only)</li>
    <li>Ph.D. in Computer Science</li>
  </ul>
  <h4>Human-Computer Interaction</h4>
  <ul>
    <li>Master of Human-Computer Interaction</li>
  </ul>
</main>
"""


def _fetcher(url: str) -> str:
    assert url == CATALOG_FETCH_URL
    return CATALOG_HTML


def test_cmu_adapter_discovers_masters_across_colleges() -> None:
    catalog = CMUAdapter(
        minimum_expected_programmes=3, maximum_expected_programmes=4
    ).parse_catalog_from_fetcher(_fetcher)

    assert {programme.name for programme in catalog.programmes} == {
        "M.S. in Biomedical Engineering",
        "MS in Computer Science",
        "Master of Human-Computer Interaction",
    }
    assert {programme.faculty for programme in catalog.programmes} == {
        "College of Engineering",
        "School of Computer Science",
    }


def test_cmu_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = CMUAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )
    computer_science = next(
        item for item in catalog.programmes if item.name == "MS in Computer Science"
    )

    assert computer_science.id == "cmu-computer-science-ms"
    assert computer_science.degree_type == "MS"
    assert computer_science.faculty == "School of Computer Science"


def test_cmu_adapter_excludes_explicitly_internal_fifth_year_degree() -> None:
    catalog = CMUAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert all("5th Year Scholars" not in item.name for item in catalog.programmes)


def test_cmu_adapter_keeps_department_specific_dates_uninferred() -> None:
    catalog = CMUAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert catalog.application_opens_at is None
    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "department-specific" in programme.deadline_text
        for programme in catalog.programmes
    )


def test_cmu_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 reviewable master's"):
        CMUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(_fetcher)
