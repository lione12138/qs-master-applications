from __future__ import annotations

from gradwindow.programme_adapters.tudelft import (
    CATALOG_URL,
    DATES_URL,
    TUDelftAdapter,
)


def test_tudelft_adapter_extracts_msc_windows() -> None:
    catalog_html = """
    <html><body>
      <a href="/en/education/programmes/masters/ae/msc-aerospace-engineering">
        English | 2 years | Full-time MSc Aerospace Engineering
      </a>
      <a href="/en/education/programmes/masters/cie/msc-civil-engineering">
        English | 2 years | Full-time MSc Civil Engineering
      </a>
      <a href="/en/education/programmes/masters/tm/msc-technical-medicine">
        Dutch | 3 years | Full-time MSc Technical Medicine
      </a>
    </body></html>
    """
    dates_html = """
    <html><body>
      <table>
        <tr>
          <td>15 October</td>
          <td>Intake of applications for MSc programmes</td>
        </tr>
        <tr>
          <td>15 January (23:59 CET)</td>
          <td>
            Application deadline for Non-EU/EFTA applicants for the MSc programmes
            Aerospace Engineering Applied Mathematics Computer Science
          </td>
        </tr>
        <tr>
          <td>1 April (23:59 CEST)</td>
          <td>
            Application deadline non-EU/EFTA all other MSc programmes
            Application deadline EU/EFTA applicants all MSc programmes
          </td>
        </tr>
      </table>
    </body></html>
    """
    pages = {
        CATALOG_URL: catalog_html,
        DATES_URL: dates_html,
    }

    catalog = TUDelftAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
        lambda url: pages[url]
    )

    assert [programme.name for programme in catalog.programmes] == [
        "MSc Aerospace Engineering",
        "MSc Civil Engineering",
    ]
    assert [
        (
            window.round,
            window.applicant_categories,
            window.opens_at,
            window.closes_at,
            window.source_url,
        )
        for window in catalog.programmes[0].windows
    ] == [
        (
            "Non-EU/EFTA early MSc deadline",
            ["non-eu-efta"],
            "2026-10-15",
            "2027-01-15",
            DATES_URL,
        ),
        (
            "EU/EFTA MSc deadline",
            ["eu-efta"],
            "2026-10-15",
            "2027-04-01",
            DATES_URL,
        ),
    ]
    assert [
        (
            window.round,
            window.applicant_categories,
            window.opens_at,
            window.closes_at,
            window.source_url,
        )
        for window in catalog.programmes[1].windows
    ] == [
        (
            "Main MSc deadline",
            ["all"],
            "2026-10-15",
            "2027-04-01",
            DATES_URL,
        )
    ]
