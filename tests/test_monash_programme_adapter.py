from __future__ import annotations

from gradwindow.programme_adapters.monash import CATALOG_URL, MonashAdapter

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.monash.edu/study/courses/find-a-course/business-analytics-b6022</loc></url>
  <url><loc>https://www.monash.edu/study/courses/find-a-course/bioinformatics-m6049</loc></url>
  <url><loc>https://www.monash.edu/study/courses/find-a-course/computer-science-c2001</loc></url>
</urlset>
"""

BUSINESS_ANALYTICS = """
<html><head><meta property="og:title" content="Business Analytics - B6022 - Study at Monash" /></head>
<body><h1>Business Analytics - B6022</h1><p>Master's degree</p>
<p>The Master of Business Analytics is designed for flexibility.</p>
<h3>Semester one (February)</h3><p>2027 intake:</p>
<ul><li>Round 1 applications close 30 July 2026</li>
<li>Round 2 applications close 30 September 2026</li></ul>
</body></html>
"""

BIOINFORMATICS = """
<html><head><meta property="og:title" content="Bioinformatics - M6049 - Study at Monash" /></head>
<body><h1>Bioinformatics - M6049</h1><p>Master's degree</p>
<p>The Master of Bioinformatics equips you with advanced computational knowledge.</p>
<h3>Making the application</h3><p>Apply directly to Monash using course code M6049.</p>
</body></html>
"""


def test_monash_adapter_discovers_confirmed_masters_and_exact_rounds() -> None:
    adapter = MonashAdapter(minimum_expected_programmes=2, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return SITEMAP
        if url.endswith("business-analytics-b6022"):
            return BUSINESS_ANALYTICS
        if url.endswith("bioinformatics-m6049"):
            return BIOINFORMATICS
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "monash-master-of-bioinformatics-m6049",
        "monash-master-of-business-analytics-b6022",
    ]
    analytics = catalog.programmes[1]
    assert analytics.name == "Master of Business Analytics"
    assert analytics.parse_status == "incomplete"
    assert [
        (window.round, window.closes_at, window.intake, window.opens_at)
        for window in analytics.windows
    ] == [
        ("Round 1 applications", "2026-07-30", "Semester 1 2027", None),
        ("Round 2 applications", "2026-09-30", "Semester 1 2027", None),
    ]
    bioinformatics = catalog.programmes[0]
    assert bioinformatics.name == "Master of Bioinformatics"
    assert bioinformatics.parse_status == "no-deadline"
    assert bioinformatics.windows == []
