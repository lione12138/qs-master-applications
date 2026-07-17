from __future__ import annotations

import pytest

from gradwindow.programme_adapters.umich import CATALOG_URL, UMichAdapter

CATALOG_HTML = """
<table id="footable_3774">
  <thead><tr>
    <th>Program Name</th><th>Campus</th><th>School/College</th>
    <th>Degree Types</th><th>Application Deadline</th>
    <th>Application Code</th><th>Program Website</th>
  </tr></thead>
  <tbody>
    <tr>
      <td>Computer Science and Engineering</td><td>Ann Arbor</td>
      <td>Engineering</td><td>Doctoral, Master’s</td>
      <td>Fall: December 15 (Ph.D.), January 15 (M.S., M.S.E.)</td>
      <td>MS/MSE (00148), PhD (00147)</td>
      <td><a href="https://cse.engin.umich.edu/academics/graduate/graduate-programs/?utm_source=rackham">Go to Computer Science and Engineering</a></td>
    </tr>
    <tr>
      <td>Quantitative Finance and Risk Management</td><td>Ann Arbor</td>
      <td>Literature, Science, and the Arts</td><td>Master’s, AMDP</td>
      <td>Fall: February 9</td><td>MS (02130), AMDP (02131)</td>
      <td><a href="https://lsa.umich.edu/stats/masters_students/mastersprograms/quantitative-finance-program.html">Go to Quantitative Finance and Risk Management</a></td>
    </tr>
    <tr>
      <td>Industrial and Systems Engineering</td><td>Dearborn</td>
      <td>Engineering (Dearborn)</td><td>Master’s</td><td></td>
      <td>MS</td><td><a href="https://umdearborn.edu/ise">Go to ISE</a></td>
    </tr>
    <tr>
      <td>Economics</td><td>Ann Arbor</td><td>Literature, Science, and the Arts</td>
      <td>Doctoral</td><td>Fall: December 1</td><td>PhD (00165)</td>
      <td><a href="https://lsa.umich.edu/econ/doctoral-program.html">Go to Economics</a></td>
    </tr>
  </tbody>
</table>
"""


def _fetcher(url: str) -> str:
    assert url == CATALOG_URL
    return CATALOG_HTML


def test_umich_adapter_discovers_only_ann_arbor_masters_programmes() -> None:
    catalog = UMichAdapter(
        minimum_expected_programmes=2, maximum_expected_programmes=3
    ).parse_catalog_from_fetcher(_fetcher)

    assert {programme.name for programme in catalog.programmes} == {
        "Computer Science and Engineering",
        "Quantitative Finance and Risk Management",
    }
    assert {programme.faculty for programme in catalog.programmes} == {
        "Engineering",
        "Literature, Science, and the Arts",
    }


def test_umich_adapter_preserves_existing_cse_identity_and_degree_types() -> None:
    catalog = UMichAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
        _fetcher
    )
    cse = next(
        item
        for item in catalog.programmes
        if item.name == "Computer Science and Engineering"
    )

    assert cse.id == "michigan-computer-science-engineering-mse"
    assert cse.degree_type == "MS / MSE"
    assert cse.source_url == (
        "https://cse.engin.umich.edu/academics/graduate/graduate-programs/"
    )


def test_umich_adapter_keeps_yearless_deadlines_as_monitoring_evidence() -> None:
    catalog = UMichAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
        _fetcher
    )

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert "February 9" in next(
        item.deadline_text
        for item in catalog.programmes
        if item.name == "Quantitative Finance and Risk Management"
    )


def test_umich_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(
        ValueError, match="only contained 2 Ann Arbor master's programmes"
    ):
        UMichAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(_fetcher)


def test_umich_adapter_retries_the_official_page_with_a_cache_buster() -> None:
    attempted = []

    def fetcher(url: str) -> str:
        attempted.append(url)
        if url == CATALOG_URL:
            raise RuntimeError("intermittent Cloudflare block")
        return CATALOG_HTML

    catalog = UMichAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
        fetcher
    )

    assert len(catalog.programmes) == 2
    assert attempted == [CATALOG_URL, "https://rackham.umich.edu/?p=3775"]
