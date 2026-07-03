from __future__ import annotations

from gradwindow.programme_adapters.glasgow import GlasgowAdapter

GLASGOW_HTML = """
<html><body><ul class="programme-list">
  <li><a href="/postgraduate/taught/computingscience/">Computing Science [MSc]</a></li>
  <li><a href="/postgraduate/taught/advanced-statistics/">Advanced Statistics [MSc]</a></li>
  <li><a href="/postgraduate/taught/ai-law-the-creative-economy/">AI Law &amp; the Creative Economy [PgCert]</a></li>
  <li><a href="/postgraduate/taught/art-history/">Art History [MLitt]</a></li>
</ul></body></html>
"""

GLASGOW_DETAIL = """
<html><body>
  <h2>Application deadlines</h2>
  <p>International &amp; EU applicants</p>
  <p>Round 1 application dates: 1 October 2025 to 5 November 2025</p>
  <p>Round 2 application dates: 6 November 2025 to 17 December 2025</p>
  <p>Home applicants 21 August 2026</p>
</body></html>
"""


def test_glasgow_adapter_extracts_master_programmes() -> None:
    catalog = GlasgowAdapter(minimum_expected_programmes=1).parse_catalog(GLASGOW_HTML)

    assert [item.id for item in catalog.programmes] == [
        "glasgow-advanced-statistics-msc",
        "glasgow-art-history-mlitt",
        "glasgow-computing-science-msc",
    ]
    computing = next(
        item for item in catalog.programmes if item.id.endswith("science-msc")
    )
    assert computing.name == "MSc Computing Science"
    assert computing.windows == []
    assert computing.parse_status == "no-deadline"


def test_glasgow_adapter_extracts_detail_page_rounds() -> None:
    def fetcher(url: str) -> str:
        return GLASGOW_DETAIL if url.endswith("/computingscience/") else GLASGOW_HTML

    catalog = GlasgowAdapter(minimum_expected_programmes=1).parse_catalog_from_fetcher(
        fetcher
    )

    computing = next(
        item
        for item in catalog.programmes
        if item.id == "glasgow-computing-science-msc"
    )
    assert [
        (window.round, window.applicant_categories, window.opens_at, window.closes_at)
        for window in computing.windows
    ] == [
        (
            "International and EU round 1",
            ["international-and-eu"],
            "2025-10-01",
            "2025-11-05",
        ),
        (
            "International and EU round 2",
            ["international-and-eu"],
            "2025-11-06",
            "2025-12-17",
        ),
        ("Home applicants", ["domestic-students"], None, "2026-08-21"),
    ]
    assert computing.parse_status == "incomplete"
