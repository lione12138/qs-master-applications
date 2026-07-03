from __future__ import annotations

from gradwindow.programme_adapters.cambridge import CambridgeAdapter

CAMBRIDGE_HTML = """
<html><body><table>
  <thead><tr><th>Course</th><th>Course Level</th><th>Taught/Research</th><th>Course Length</th></tr></thead>
  <tbody>
    <tr><td><a href="/courses/directory/egcempace">Advanced Chemical Engineering - Closed this cycle</a> MPhil</td><td>Master's</td><td>Taught</td><td>11 months full-time</td></tr>
    <tr><td><a href="/courses/directory/egegpdtwo">2D Materials of Tomorrow</a> PhD</td><td>Doctoral</td><td>Research</td><td>3 years</td></tr>
    <tr><td><a href="/courses/directory/icicdpgmf">(flexible) in Genomic Medicine - Closed this cycle</a> PGDip</td><td>Diploma</td><td></td><td>9 months</td></tr>
  </tbody>
</table></body></html>
"""

CAMBRIDGE_DETAIL = """
<html><body>
  <h1>MPhil in Advanced Computer Science</h1>
  <div>Applications open Sep. 3, 2025 Application deadline Feb. 26, 2026 Course starts Oct. 5, 2026</div>
</body></html>
"""


def test_cambridge_adapter_extracts_taught_master_rows() -> None:
    catalog = CambridgeAdapter(minimum_expected_programmes=1).parse_catalog(
        CAMBRIDGE_HTML
    )

    assert len(catalog.programmes) == 1
    programme = catalog.programmes[0]
    assert programme.id == "cambridge-advanced-chemical-engineering-mphil"
    assert programme.name == "MPhil in Advanced Chemical Engineering"
    assert programme.windows == []
    assert programme.parse_status == "no-deadline"


def test_cambridge_adapter_can_fetch_paginated_directory() -> None:
    first_page = CAMBRIDGE_HTML.replace(
        "</body>",
        '<nav class="pager"><a href="?page=1">Last page</a></nav></body>',
    )
    second_page = CAMBRIDGE_HTML.replace(
        "Advanced Chemical Engineering",
        "Advanced Computer Science",
    ).replace("egcempace", "cscsmpacs")

    def fetcher(url: str) -> str:
        if "cscsmpacs" in url or "egcempace" in url:
            return CAMBRIDGE_DETAIL
        return second_page if "page=1" in url else first_page

    catalog = CambridgeAdapter(
        minimum_expected_programmes=2
    ).parse_catalog_from_fetcher(fetcher)

    assert {item.id for item in catalog.programmes} == {
        "cambridge-advanced-chemical-engineering-mphil",
        "cambridge-advanced-computer-science-mphil",
    }
    assert all(item.parse_status == "parsed" for item in catalog.programmes)
    assert catalog.programmes[0].windows[0].opens_at == "2025-09-03"
    assert catalog.programmes[0].windows[0].closes_at == "2026-02-26"
    assert catalog.programmes[0].windows[0].intake == "Michaelmas 2026"
