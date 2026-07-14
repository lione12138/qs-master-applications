from __future__ import annotations

import json

from gradwindow.programme_adapters.ntu import (
    APPLICATION_URL,
    NTUAdapter,
    catalog_page_url,
)

PAGE_ONE = {
    "totalPages": 2,
    "totalItems": 4,
    "items": [
        {
            "title": "Master of Science in Maritime Studies",
            "url": "/education/graduate-programme/master-of-science-in-maritime-studies",
            "tag": "Science | Sustainability",
            "description": "Study maritime policy and operations.",
        },
        {
            "title": "Master of Computing In Applied AI (MCAAI)",
            "url": "/education/graduate-programme/master-of-computing-in-applied-ai-mcaai",
            "tag": "Computing",
            "description": "Applied artificial intelligence coursework.",
        },
    ],
}

PAGE_TWO = {
    "totalPages": 2,
    "totalItems": 4,
    "items": [
        {
            "title": "Master of Arts in Translation and Interpretation",
            "url": "/education/graduate-programme/master-of-arts-in-translation-and-interpretation",
            "tag": "Humanities",
            "description": "Professional translation and interpretation.",
        },
        {
            "title": "Master of Science Technopreneurship and Innovation Programme (CN)",
            "url": "/education/graduate-programme/technopreneurship-cn",
            "tag": "Business | Innovation/Entrepreneurship",
            "description": "Chinese-language programme.",
        },
    ],
}

APPLICATION_HTML = """
<html><body>
  <table>
    <tr><th>Admission Year &amp; Intake</th><th>Admission Date</th>
      <th>Programme Name</th><th>Opening Date</th><th>Closing Date</th></tr>
    <tr><td>2026 / Semester 2</td><td>11-Jan-27</td>
      <td>202 - MSC(MARITIME STUDIES)</td><td>1-Jul-26</td><td>31-Aug-26</td></tr>
    <tr><td>2026 / Semester 2</td><td>11-Jan-27</td>
      <td>282 - MASTER OF ARTS (TRANSLATION &amp; INTERPRETATION)</td>
      <td>1-Jul-26</td><td>31-Aug-26</td></tr>
  </table>
</body></html>
"""


def _fetcher(url: str) -> str:
    if url == catalog_page_url(1):
        return json.dumps(PAGE_ONE)
    if url == catalog_page_url(2):
        return json.dumps(PAGE_TWO)
    if url == APPLICATION_URL:
        return APPLICATION_HTML
    raise AssertionError(url)


def test_ntu_adapter_combines_catalogue_with_live_application_windows() -> None:
    catalog = NTUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
        _fetcher
    )

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "ntu-applied-artificial-intelligence-mcomp",
        "ntu-maritime-studies-msc",
        "ntu-technopreneurship-and-innovation-programme-cn-msc",
        "ntu-translation-and-interpretation-ma",
    ]
    assert catalog.programmes[0].windows == []
    assert catalog.programmes[0].parse_status == "no-deadline"
    maritime = catalog.programmes[1]
    assert maritime.parse_status == "parsed"
    assert [
        (
            window.intake,
            window.round,
            window.opens_at,
            window.closes_at,
            window.applicant_categories,
        )
        for window in maritime.windows
    ] == [
        (
            "January 2027",
            "Semester 2",
            "2026-07-01",
            "2026-08-31",
            ["all"],
        )
    ]
    assert catalog.programmes[3].windows[0].closes_at == "2026-08-31"


def test_ntu_adapter_rejects_truncated_catalogue() -> None:
    try:
        NTUAdapter(minimum_expected_programmes=5).parse_catalog_from_fetcher(_fetcher)
    except ValueError as exc:
        assert "only contained 4" in str(exc)
    else:
        raise AssertionError("Truncated NTU catalogue was accepted")
