from __future__ import annotations

import pytest

from gradwindow.programme_adapters.edinburgh import (
    CATALOG_URL,
    EdinburghAdapter,
    _catalogue_programmes,
)

CATALOGUE = """
<html><body>
  <div id="psw-search-result-count">4</div>
  <div class="result"><h3><a href="/programmes/postgraduate-taught/129-applied-psychology-healthcare-for-children-and-young-people">Applied Psychology (Healthcare) for Children and Young People MSc</a></h3></div>
  <div class="result"><h3><a href="/programmes/postgraduate-taught/98-education">Education MSc</a></h3></div>
  <div class="result"><h3><a href="/programmes/postgraduate-taught/272-economics-econometrics-finance">Economics / Economics (Econometrics) / Economics (Finance) MSc</a></h3></div>
  <div class="result"><h3><a href="/programmes/postgraduate-taught/634-social-work-certificate">Advanced Social Work Studies PgCert</a></h3></div>
</body></html>
"""

EXACT = """
<html><body>
  <div class="pgt-programme-metadata__study-options"><ul><li>MSc | 2 years | Start date: February 2027</li></ul></div>
  <div class="pgt-programme-metadata__key-facts">
    <div class="pgt-programme-metadata__item"><b>School</b><p>School of Health in Social Science</p></div>
    <div class="pgt-programme-metadata__item"><b>College</b><p>College of Arts, Humanities and Social Sciences</p></div>
  </div>
  <div class="pgt-programme-applying__when">
    <h3>When to apply</h3>
    <table><thead><tr><th>Applications open</th><th>Application deadline</th></tr></thead>
      <tbody><tr><td>17 June 2026</td><td>8 July 2026</td></tr></tbody>
    </table>
  </div>
</body></html>
"""

STANDARD = """
<html><body>
  <div class="pgt-programme-metadata__study-options"><p>Start date: multiple dates</p></div>
  <div class="pgt-programme-applying__when">
    <table><thead><tr><th>Programme start date</th><th>Application deadline</th></tr></thead>
      <tbody><tr><td>14 September 2026</td><td>30 July 2026</td></tr></tbody>
    </table>
  </div>
</body></html>
"""

ROUNDS = """
<html><body>
  <div class="pgt-programme-metadata__study-options"><p>MSc | 1 year | Start date: September 2026</p></div>
  <div class="pgt-programme-applying__when">
    <p>This programme is not currently open. Applications for the next intake usually open in October.</p>
    <table><tbody>
      <tr><td><strong>Round</strong></td><td><strong>Application deadline</strong></td><td><strong>Decisions made</strong></td></tr>
      <tr><td>1</td><td>15 December</td><td>1 March</td></tr>
      <tr><td>2</td><td>31 March</td><td>31 May</td></tr>
    </tbody></table>
    <p>The Round 2 application deadline has been extended to 1 June 2026.</p>
  </div>
</body></html>
"""


def test_edinburgh_adapter_reads_catalogue_and_deadline_table_variants() -> None:
    adapter = EdinburghAdapter(minimum_expected_programmes=3, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOGUE
        if "/129-" in url:
            return EXACT
        if "/98-" in url:
            return STANDARD
        if "/272-" in url:
            return ROUNDS
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert [programme.id for programme in catalog.programmes] == [
        "edinburgh-applied-psychology-healthcare-for-children-and-young-people-msc",
        "edinburgh-economics-economics-econometrics-economics-finance-msc",
        "edinburgh-education-msc",
    ]
    exact = catalog.programmes[0]
    assert exact.parse_status == "parsed"
    assert exact.faculty == "College of Arts, Humanities and Social Sciences"
    assert exact.department == "School of Health in Social Science"
    assert [
        (window.opens_at, window.closes_at, window.intake) for window in exact.windows
    ] == [("2026-06-17", "2026-07-08", "February 2027")]

    rounds = catalog.programmes[1]
    assert rounds.parse_status == "incomplete"
    assert [(window.round, window.closes_at) for window in rounds.windows] == [
        ("Round 1", "2025-12-15"),
        ("Round 2", "2026-03-31"),
        ("Extended application deadline", "2026-06-01"),
    ]
    standard = catalog.programmes[2]
    assert standard.parse_status == "incomplete"
    assert [(window.closes_at, window.intake) for window in standard.windows] == [
        ("2026-07-30", "September 2026")
    ]


def test_edinburgh_adapter_keeps_temporarily_failed_detail_page() -> None:
    adapter = EdinburghAdapter(minimum_expected_programmes=3, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOGUE
        raise RuntimeError("temporary block")

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert len(catalog.programmes) == 3
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "temporary block" in programme.deadline_text for programme in catalog.programmes
    )


def test_edinburgh_adapter_rejects_implausibly_small_catalogue() -> None:
    adapter = EdinburghAdapter(minimum_expected_programmes=4, detail_workers=1)

    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        adapter.parse_catalog_from_fetcher(lambda url: CATALOGUE)


def test_edinburgh_catalogue_keeps_online_variant_and_edition_path() -> None:
    html = """
    <div class="result"><h3><a href="/programmes/postgraduate-taught/267-business-administration-master-of">Business Administration, Master of MBA</a></h3></div>
    <div class="result"><h3><a href="/programmes/postgraduate-taught/1076-business-administration-master-of-online-learning">Business Administration, Master of MBA</a></h3></div>
    <div class="result"><h3><a href="/programmes/postgraduate-taught/2027/1045-comparative-education-and-international-development-ceid">Comparative Education and International Development (CEID) MSc</a></h3></div>
    """

    programmes = _catalogue_programmes(html)

    assert [programme.id for programme in programmes] == [
        "edinburgh-business-administration-master",
        "edinburgh-business-administration-online-learning-master",
        "edinburgh-comparative-education-and-international-development-ceid-msc",
    ]
