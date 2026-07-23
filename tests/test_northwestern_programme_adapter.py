from __future__ import annotations

import pytest

from gradwindow.programme_adapters.northwestern import (
    BIENEN_TIMELINE_URL,
    CATALOG_URL,
    NorthwesternAdapter,
)

CATALOG_HTML = """
<table>
  <tr><th>Academic Program</th><th>School</th><th>Degree Type</th>
      <th>Degree filter</th><th>Interest filter</th><th>School filter</th></tr>
  <tr><td><a href="https://www.mccormick.northwestern.edu/computer-science/academics/graduate/masters/?utm_source=nu">Computer Science MS</a></td>
      <td>McCormick</td><td>MS</td><td>Masters Degree</td><td>Technology</td><td>Engineering School</td></tr>
  <tr><td><a href="https://www.music.northwestern.edu/academics/areas-of-study/brass">Brass Performance MM</a></td>
      <td>Bienen</td><td>MM</td><td>Masters Degree</td><td>Music</td><td>Music School</td></tr>
  <tr><td><a href="https://sps.northwestern.edu/masters/data-science/">Data Science</a></td>
      <td>SPS</td><td>MS</td><td>Masters Degree</td><td>Technology</td><td>Professional Studies</td></tr>
  <tr><td><a href="https://sps.northwestern.edu/masters/data-science/?duplicate=1">Data Science duplicate</a></td>
      <td>SPS</td><td>MS</td><td>Masters Degree</td><td>Technology</td><td>Professional Studies</td></tr>
  <tr><td><a href="/doctoral/example">Doctoral example</a></td>
      <td>TGS</td><td>PhD</td><td>Doctoral Degree</td><td>Science</td><td>Graduate School</td></tr>
</table>
"""

TIMELINE_HTML = """
<main>
  <p>The 2027 MM &amp; DMA application will be available August 1, 2026.</p>
  <h3>Fall 2027 Graduate Application Timeline</h3>
  <p>August 1</p><p>Graduate Application available online</p>
  <p>December 1</p><p>Graduate Application and prescreening materials (if applicable) due</p>
</main>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url == BIENEN_TIMELINE_URL:
        return TIMELINE_HTML
    raise AssertionError(url)


def test_northwestern_adapter_discovers_unique_master_programmes() -> None:
    catalog = NorthwesternAdapter(
        minimum_expected_programmes=3, maximum_expected_programmes=4
    ).parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {programme.name for programme in catalog.programmes} == {
        "Brass Performance MM",
        "Computer Science MS",
        "Data Science",
    }


def test_northwestern_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = NorthwesternAdapter(
        minimum_expected_programmes=3
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.name == "Computer Science MS"
    )

    assert programme.id == "northwestern-computer-science-ms"


def test_northwestern_adapter_assigns_exact_bienen_window_only_to_mm() -> None:
    catalog = NorthwesternAdapter(
        minimum_expected_programmes=3
    ).parse_catalog_from_fetcher(_fetcher)
    music = next(item for item in catalog.programmes if item.faculty == "Bienen")
    non_music = [item for item in catalog.programmes if item.faculty != "Bienen"]

    assert music.parse_status == "parsed"
    assert len(music.windows) == 1
    assert music.windows[0].opens_at == "2026-08-01"
    assert music.windows[0].closes_at == "2026-12-01"
    assert music.windows[0].intake == "Fall 2027"
    assert all(item.windows == [] for item in non_music)
    assert all(item.parse_status == "no-deadline" for item in non_music)


def test_northwestern_adapter_does_not_reuse_an_old_bienen_cycle() -> None:
    catalog = NorthwesternAdapter(
        minimum_expected_programmes=3,
        target_intake_year=2028,
    ).parse_catalog_from_fetcher(_fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)


def test_northwestern_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 unique master's programmes"):
        NorthwesternAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
            _fetcher
        )
