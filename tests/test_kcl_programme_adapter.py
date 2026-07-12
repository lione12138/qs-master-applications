from __future__ import annotations

import json

from gradwindow.programme_adapters.kcl import CATALOG_URL, SITEMAP_URL, KCLAdapter

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.kcl.ac.uk/sitemaps/study</loc></sitemap>
</sitemapindex>
"""

STUDY_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.kcl.ac.uk/study/postgraduate-taught/courses/clinical-pharmacology-msc</loc></url>
  <url><loc>https://www.kcl.ac.uk/study/postgraduate-taught/courses/advanced-clinical-practice-msc-pg-dip-pg-cert</loc></url>
  <url><loc>https://www.kcl.ac.uk/study/postgraduate-taught/courses/clinical-pharmacology-msc/fees</loc></url>
  <url><loc>https://www.kcl.ac.uk/study/undergraduate/courses/pharmacology-bsc</loc></url>
</urlset>
"""

CLINICAL_PHARMACOLOGY = """
<html><head><title>Clinical Pharmacology MSc - Entry Requirements | King's College London</title></head>
<body>
  <h2>Application closing date guidance</h2>
  <p>The final application deadlines for this programme are:</p>
  <ul>
    <li>Overseas (international) fee status: 25 July 2026 (23:59 UK time)</li>
    <li>Home fee status: 25 August 2026 (23:59 UK time)</li>
  </ul>
  <h2>Taught in</h2><a>Faculty of Life Sciences &amp; Medicine</a>
  <a>School of Cancer &amp; Pharmaceutical Sciences</a>
  <h2>Base campus</h2>
</body></html>
"""

ADVANCED_CLINICAL_PRACTICE = """
<html><head><title>Advanced Clinical Practice MSc, PG Dip - Entry Requirements | King's College London</title></head>
<body>
  <h2>Application closing date guidance</h2>
  <h3>January 2026 intake:</h3>
  <p>Overseas (international) fee status: 20 October 2025 (23:59 UK time)</p>
  <p>Home fee status: 20 November 2025 (23:59 UK time)</p>
  <h3>September 2026 intake:</h3>
  <p>Our first application deadline is on 9 March 2026 (23:59 UK time).</p>
  <p>Overseas (international) fee status: 25 July 2026 (23:59 UK time)</p>
  <p>Home fee status: 25 August 2026 (23:59 UK time)</p>
  <h2>Key Links</h2>
</body></html>
"""

SINGLE_FACULTY = """
<html><head><title>Accounting &amp; Finance - Entry Requirements | King's College London</title></head>
<body>
  <div class="FacultiesAndDepartmentsstyled__FacultiesAndDepartmentsStyled-sc-test">
    <h2>Taught in</h2><a>King’s Business School</a>
  </div>
  <footer><a>Degree courses Footer navigation link</a></footer>
</body></html>
"""


def test_kcl_adapter_reads_sitemap_and_course_specific_deadlines() -> None:
    adapter = KCLAdapter(minimum_expected_programmes=2, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == SITEMAP_URL:
            return SITEMAP_INDEX
        if url.endswith("/study"):
            return STUDY_SITEMAP
        if "clinical-pharmacology-msc/requirements" in url:
            return CLINICAL_PHARMACOLOGY
        if "advanced-clinical-practice" in url:
            return ADVANCED_CLINICAL_PRACTICE
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "kcl-advanced-clinical-practice-msc-pg-dip",
        "kcl-clinical-pharmacology-msc",
    ]
    clinical = catalog.programmes[1]
    assert clinical.name == "Clinical Pharmacology MSc"
    assert clinical.degree_type == "MSc"
    assert clinical.parse_status == "incomplete"
    assert clinical.faculty == "Faculty of Life Sciences & Medicine"
    assert [
        (window.applicant_categories, window.closes_at, window.intake)
        for window in clinical.windows
    ] == [
        (["international"], "2026-07-25", "September 2026"),
        (["home"], "2026-08-25", "September 2026"),
    ]

    advanced = catalog.programmes[0]
    assert [
        (window.round, window.applicant_categories, window.closes_at, window.intake)
        for window in advanced.windows
    ] == [
        ("Final application deadline", ["international"], "2025-10-20", "January 2026"),
        ("Final application deadline", ["home"], "2025-11-20", "January 2026"),
        ("First application deadline", ["all"], "2026-03-09", "September 2026"),
        (
            "Final application deadline",
            ["international"],
            "2026-07-25",
            "September 2026",
        ),
        ("Final application deadline", ["home"], "2026-08-25", "September 2026"),
    ]


def test_kcl_adapter_keeps_failed_detail_pages_as_no_deadline_candidates() -> None:
    adapter = KCLAdapter(minimum_expected_programmes=1, detail_workers=1)
    sitemap = """<urlset><url><loc>https://www.kcl.ac.uk/study/postgraduate-taught/courses/artificial-intelligence-msc</loc></url></urlset>"""

    def fetcher(url: str) -> str:
        if url == SITEMAP_URL:
            return sitemap
        raise RuntimeError("temporary block")

    catalogue = adapter.parse_catalog_from_fetcher(fetcher)
    programme = catalogue.programmes[0]
    assert programme.id == "kcl-artificial-intelligence-msc"
    assert programme.parse_status == "no-deadline"
    assert programme.windows == []
    assert "temporary block" in programme.deadline_text


def test_kcl_adapter_uses_dynamic_delivery_catalogue_when_sitemap_is_stale() -> None:
    adapter = KCLAdapter(minimum_expected_programmes=2, detail_workers=1)
    stale_sitemap = """<urlset><url><loc>https://www.kcl.ac.uk/study-legacy/postgraduate/</loc></url></urlset>"""
    catalogue_html = """
    <html><body>
      <script src="/_assets/static/startup-1.23.0.js"></script>
      <a href="/study/postgraduate-taught/courses/clinical-pharmacology-msc">Clinical Pharmacology</a>
    </body></html>
    """
    startup_script = """
    var alias = "kcl";
    var config = {api: "https://api-" + alias + ".cloud.contensis.com"};
    context.DELIVERY_API_CONFIG = {accessToken: "public-browser-token"};
    """
    api_payload = json.dumps(
        {
            "totalCount": 2,
            "items": [
                {
                    "sys": {
                        "uri": "/study/postgraduate-taught/courses/clinical-pharmacology-msc"
                    },
                    "entryTitle": "Clinical Pharmacology",
                },
                {
                    "sys": {
                        "uri": "/study/postgraduate-taught/courses/artificial-intelligence-msc"
                    },
                    "entryTitle": "Artificial Intelligence",
                },
            ],
        }
    )

    def fetcher(url: str) -> str:
        if url == SITEMAP_URL:
            return stale_sitemap
        if url == CATALOG_URL:
            return catalogue_html
        if url.endswith("startup-1.23.0.js"):
            return startup_script
        if "api-kcl.cloud.contensis.com" in url:
            assert "accessToken=public-browser-token" in url
            return api_payload
        if "clinical-pharmacology-msc/requirements" in url:
            return CLINICAL_PHARMACOLOGY
        if "artificial-intelligence-msc/requirements" in url:
            raise RuntimeError("not available")
        raise AssertionError(url)

    catalogue = adapter.parse_catalog_from_fetcher(fetcher)

    assert [programme.id for programme in catalogue.programmes] == [
        "kcl-artificial-intelligence-msc",
        "kcl-clinical-pharmacology-msc",
    ]
    assert [programme.name for programme in catalogue.programmes] == [
        "Artificial Intelligence MSc",
        "Clinical Pharmacology MSc",
    ]
    assert "apiTotal=2" in adapter.sitemap_diagnostics


def test_kcl_adapter_does_not_treat_footer_links_as_departments() -> None:
    adapter = KCLAdapter(minimum_expected_programmes=1, detail_workers=1)
    sitemap = """<urlset><url><loc>https://www.kcl.ac.uk/study/postgraduate-taught/courses/accounting-finance-msc</loc></url></urlset>"""

    def fetcher(url: str) -> str:
        if url == SITEMAP_URL:
            return sitemap
        if url.endswith("/requirements"):
            return SINGLE_FACULTY
        raise AssertionError(url)

    programme = adapter.parse_catalog_from_fetcher(fetcher).programmes[0]

    assert programme.faculty == "King’s Business School"
    assert programme.department == ""
