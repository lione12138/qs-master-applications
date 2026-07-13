from __future__ import annotations

from gradwindow.programme_adapters.monash import (
    CATALOG_URL,
    MARKETING_PROBE_URL,
    MonashAdapter,
)

SITEMAP_INDEX = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://handbook.monash.edu/sitemap/courses.xml</loc></sitemap>
</sitemapindex>"""

COURSE_SITEMAP = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://handbook.monash.edu/2026/courses/B6022</loc></url>
<url><loc>https://handbook.monash.edu/2026/courses/M6049</loc></url>
<url><loc>https://handbook.monash.edu/2026/courses/C2001</loc></url>
</urlset>"""

BUSINESS_HANDBOOK = """<html><head><title>B6022 - Master of Business Analytics - Monash University</title></head>
<body><p>Managing faculty: Faculty of Business and Economics Credit points: 96</p>
<p>Monash course type: Masters degree (Coursework)</p></body></html>"""

BIOINFORMATICS_HANDBOOK = """<html><head><title>M6049 - Master of Bioinformatics - Monash University</title></head>
<body><p>Managing faculty: Faculty of Medicine, Nursing and Health Sciences Credit points: 96</p>
<p>Monash course type: Masters degree (Coursework)</p></body></html>"""

BUSINESS_MARKETING = """<html><body><p>2027 intake:</p>
<h3>Semester one (February)</h3>
<p>Round 1 applications close 30 July 2026.</p>
<p>Round 2 applications close 30 September 2026.</p></body></html>"""


def test_monash_adapter_uses_handbook_catalogue_and_optional_marketing_dates() -> None:
    adapter = MonashAdapter(minimum_expected_programmes=2, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return SITEMAP_INDEX
        if url.endswith("courses.xml"):
            return COURSE_SITEMAP
        if url.endswith("/B6022"):
            return BUSINESS_HANDBOOK
        if url.endswith("/M6049"):
            return BIOINFORMATICS_HANDBOOK
        if url == MARKETING_PROBE_URL:
            return BUSINESS_MARKETING
        if url.endswith("bioinformatics-m6049"):
            raise RuntimeError("marketing site blocked")
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "monash-master-of-bioinformatics-m6049",
        "monash-master-of-business-analytics-b6022",
    ]
    analytics = catalog.programmes[1]
    assert analytics.faculty == "Faculty of Business and Economics"
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
