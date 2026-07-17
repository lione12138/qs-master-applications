from __future__ import annotations

import pytest

from gradwindow.programme_adapters.unsw import CATALOG_URL, UNSWAdapter

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="https://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.unsw.edu.au/study/postgraduate/master-of-information-technology</loc></url>
  <url><loc>https://www.unsw.edu.au/study/postgraduate/master-of-analytics</loc></url>
  <url><loc>https://www.unsw.edu.au/study/postgraduate/master-of-analytics-marketing</loc></url>
  <url><loc>https://www.unsw.edu.au/study/postgraduate/agsm-mba-master-of-business-administration</loc></url>
  <url><loc>https://www.unsw.edu.au/study/postgraduate/master-of-biomedical-engineering</loc></url>
  <url><loc>https://www.unsw.edu.au/study/postgraduate/graduate-certificate-in-analytics</loc></url>
</urlset>
"""

INFORMATION_TECHNOLOGY_HTML = """
<html><head>
  <meta name="degree-program-code" content="8543" />
  <meta name="degree-faculty" content="Faculty of Engineering" />
  <meta name="degree-type" content="Postgraduate" />
  <meta name="degree-single-double" content="Single Degree" />
</head><body><h1>Master of Information Technology</h1></body></html>
"""

ANALYTICS_HTML = """
<html><head>
  <meta property="og:title" content="Master of Analytics | UNSW Sydney" />
  <meta name="degree-program-code" content="8437" />
  <meta name="degree-faculty" content="UNSW Business School" />
  <meta name="degree-type" content="Postgraduate" />
  <meta name="degree-single-double" content="Single Degree" />
</head><body></body></html>
"""

ANALYTICS_MARKETING_HTML = ANALYTICS_HTML.replace(
    "Master of Analytics |", "Master of Analytics (Marketing) |"
)

MBA_HTML = """
<html><head>
  <meta name="degree-program-code" content="8350" />
  <meta name="degree-faculty" content="UNSW Business School" />
  <meta name="degree-type" content="Postgraduate" />
  <meta name="degree-single-double" content="Single Degree" />
</head><body><h1>AGSM Master of Business Administration</h1></body></html>
"""

INVALID_MASTER_HTML = """
<html><head><meta property="og:title" content="Progress needs engineers" /></head>
<body><h1>Progress needs engineers</h1></body></html>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return SITEMAP_XML
    if url.endswith("/master-of-information-technology"):
        return INFORMATION_TECHNOLOGY_HTML
    if url.endswith("/master-of-analytics"):
        return ANALYTICS_HTML
    if url.endswith("/master-of-analytics-marketing"):
        return ANALYTICS_MARKETING_HTML
    if url.endswith("/agsm-mba-master-of-business-administration"):
        return MBA_HTML
    if url.endswith("/master-of-biomedical-engineering"):
        return INVALID_MASTER_HTML
    raise AssertionError(url)


def test_unsw_adapter_discovers_and_deduplicates_official_masters() -> None:
    catalog = UNSWAdapter(
        minimum_expected_programmes=3,
        detail_workers=1,
    ).parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "unsw-8350-agsm-mba-master-of-business-administration",
        "unsw-8437-master-of-analytics",
        "unsw-information-technology-master",
    ]
    assert [programme.name for programme in catalog.programmes] == [
        "AGSM Master of Business Administration",
        "Master of Analytics",
        "Master of Information Technology",
    ]


def test_unsw_adapter_preserves_existing_it_id_and_monitoring_contract() -> None:
    catalog = UNSWAdapter(
        minimum_expected_programmes=3,
        detail_workers=1,
    ).parse_catalog_from_fetcher(_fetcher)
    by_id = {programme.id: programme for programme in catalog.programmes}
    information_technology = by_id["unsw-information-technology-master"]

    assert information_technology.degree_type == "Master"
    assert information_technology.faculty == "Faculty of Engineering"
    assert information_technology.department == ""
    assert information_technology.source_url.endswith(
        "/study/postgraduate/master-of-information-technology"
    )
    assert information_technology.application_url == information_technology.source_url
    assert information_technology.windows == []
    assert information_technology.parse_status == "no-deadline"
    assert information_technology.retrieval_method == (
        "official-sitemap-and-degree-page"
    )
    assert information_technology.evidence_quality == "official-full-text"
    assert "vary by program and intake" in information_technology.deadline_text
    assert "no dates are inferred" in information_technology.deadline_text


def test_unsw_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only produced 3 unique master's programmes"):
        UNSWAdapter(
            minimum_expected_programmes=4,
            detail_workers=1,
        ).parse_catalog_from_fetcher(_fetcher)


def test_unsw_adapter_uses_the_official_study_sitemap() -> None:
    assert CATALOG_URL == "https://www.unsw.edu.au/study.sitemap.xml"
