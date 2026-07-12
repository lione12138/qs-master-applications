from __future__ import annotations

from gradwindow.programme_adapters.sydney import CATALOG_URL, DATES_URL, SydneyAdapter

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.sydney.edu.au/courses/courses/pc/master-of-data-science.html</loc></url>
  <url><loc>https://www.sydney.edu.au/courses/courses/pc/executive-master-of-business-administration.html</loc></url>
  <url><loc>https://www.sydney.edu.au/courses/courses/pr/master-of-philosophy.html</loc></url>
</urlset>
"""

DATES = """
<html><body><h3>Postgraduate</h3><table>
  <tr><th></th><th>Semester 1 (Feb)</th><th>Semester 2 (Aug)</th></tr>
  <tr><th>Domestic students</th><td>31 January of the commencing year</td><td>15 July of the commencing year</td></tr>
  <tr><th>International students</th><td>18 December of the year prior to commencement</td><td>29 May of the commencing year</td></tr>
</table></body></html>
"""

DATA_SCIENCE = """
<html><head>
  <meta property="og:title" content="Master of Data Science | The University of Sydney" />
  <meta name="course:faculty" content="Faculty of Engineering" />
</head>
<body><h1>Course details</h1><p>For domestic students</p>
<h2>Course-specific dates</h2>
<p>2027 Start year (February intake) applications due 30 November 2026.</p>
</body></html>
"""


def test_sydney_adapter_discovers_masters_and_parses_specific_deadline() -> None:
    adapter = SydneyAdapter(minimum_expected_programmes=2, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return SITEMAP
        if url == DATES_URL:
            return DATES
        if url.endswith("master-of-data-science.html"):
            return DATA_SCIENCE
        if url.endswith("executive-master-of-business-administration.html"):
            raise RuntimeError("temporary block")
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "sydney-executive-master-of-business-administration",
        "sydney-master-of-data-science",
    ]
    data_science = catalog.programmes[1]
    assert data_science.name == "Master of Data Science"
    assert data_science.faculty == "Faculty of Engineering"
    assert [
        (window.intake, window.closes_at, window.applicant_categories)
        for window in data_science.windows
    ] == [("Semester 1 2027", "2026-11-30", ["domestic-students"])]
    assert data_science.parse_status == "incomplete"

    executive = catalog.programmes[0]
    assert len(executive.windows) == 4
    assert {
        (window.intake, window.closes_at, tuple(window.applicant_categories))
        for window in executive.windows
    } == {
        ("Semester 1 2027", "2027-01-31", ("domestic-students",)),
        ("Semester 2 2027", "2027-07-15", ("domestic-students",)),
        ("Semester 1 2027", "2026-12-18", ("international-students",)),
        ("Semester 2 2027", "2027-05-29", ("international-students",)),
    }
