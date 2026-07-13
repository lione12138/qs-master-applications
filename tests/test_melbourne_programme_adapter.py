from __future__ import annotations

from gradwindow.programme_adapters.melbourne import (
    CATALOG_FETCH_URL,
    CATALOG_PAGE_URL,
    MARKETING_PROBE_URL,
    MelbourneAdapter,
)

PAGE_ONE = """<html><body>
<nav><a href="/courses?page=1">1</a><a href="/courses?page=2">2</a></nav>
<ul class="search-results">
<li class="search-results__accordion-item">
  <a class="search-results__accordion-title" href="/courses/mc-it">
    Master of Information Technology
    <span class="search-results__accordion-code">MC-IT</span>
  </a>
  <table><tr><th>Qualification type</th><td>Masters (Coursework)</td></tr></table>
</li>
<li class="search-results__accordion-item">
  <a class="search-results__accordion-title" href="/courses/mr-science">
    Master of Science
    <span class="search-results__accordion-code">MR-SCIENCE</span>
  </a>
  <table><tr><th>Qualification type</th><td>Masters (Research)</td></tr></table>
</li>
</ul></body></html>"""

PAGE_TWO = """<html><body><ul class="search-results">
<li class="search-results__accordion-item">
  <a class="search-results__accordion-title" href="/courses/mc-arch">
    Master of Architecture
    <span class="search-results__accordion-code">MC-ARCH</span>
  </a>
  <table><tr><th>Qualification type</th><td>Masters (Extended)</td></tr></table>
</li>
<li class="search-results__accordion-item">
  <a class="search-results__accordion-title" href="/courses/gc-data">
    Graduate Certificate in Data
    <span class="search-results__accordion-code">GC-DATA</span>
  </a>
  <table><tr><th>Qualification type</th><td>Graduate Certificate</td></tr></table>
</li>
<li class="search-results__accordion-item">
  <a class="search-results__accordion-title" href="/courses/mc-empa">
    Executive Master of Public Administration
    <span class="search-results__accordion-code">MC-EMPA</span>
  </a>
  <table><tr><th>Qualification type</th><td>Masters (Coursework)</td></tr></table>
</li>
</ul></body></html>"""

IT_APPLICATION_PAGE = """<html><body>
<h1>Master of Information Technology</h1>
<p>Domestic student Change</p>
<h3>Upcoming intakes and key dates</h3>
<p>Start year (February intake) applications due 30 November 2026</p>
<p>Mid-year (July intake) applications due 31 May 2027</p>
</body></html>"""


def test_melbourne_adapter_uses_handbook_origin_and_optional_course_dates() -> None:
    adapter = MelbourneAdapter(
        minimum_expected_programmes=2,
        catalog_workers=1,
        detail_workers=1,
    )

    def fetcher(url: str) -> str:
        if url == CATALOG_FETCH_URL:
            return PAGE_ONE
        if url == CATALOG_PAGE_URL.format(page=2):
            return PAGE_TWO
        if url == MARKETING_PROBE_URL:
            return IT_APPLICATION_PAGE
        if url.endswith("master-of-architecture/how-to-apply/"):
            raise RuntimeError("course page blocked")
        if url.endswith("executive-master-of-public-administration/how-to-apply/"):
            raise RuntimeError("course page blocked")
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "melbourne-executive-master-of-public-administration-mc-empa",
        "melbourne-master-of-architecture-mc-arch",
        "melbourne-master-of-information-technology-mc-it",
    ]
    _, architecture, information_technology = catalog.programmes
    assert architecture.parse_status == "no-deadline"
    assert architecture.windows == []
    assert information_technology.source_url == (
        "https://handbook.unimelb.edu.au/2026/courses/mc-it"
    )
    assert information_technology.parse_status == "incomplete"
    assert [
        (
            window.round,
            window.closes_at,
            window.intake,
            window.applicant_categories,
            window.opens_at,
        )
        for window in information_technology.windows
    ] == [
        (
            "Start year deadline",
            "2026-11-30",
            "Semester 1 2027",
            ["domestic"],
            None,
        ),
        (
            "Mid-year deadline",
            "2027-05-31",
            "Semester 2 2027",
            ["domestic"],
            None,
        ),
    ]


def test_melbourne_adapter_keeps_catalogue_when_application_pages_are_blocked() -> None:
    adapter = MelbourneAdapter(
        minimum_expected_programmes=1,
        catalog_workers=1,
        detail_workers=1,
    )

    def fetcher(url: str) -> str:
        if url == CATALOG_FETCH_URL:
            return PAGE_ONE.replace('<a href="/courses?page=2">2</a>', "")
        if url == MARKETING_PROBE_URL:
            raise RuntimeError("HTTP 403")
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert len(catalog.programmes) == 1
    assert catalog.programmes[0].name == "Master of Information Technology"
    assert catalog.programmes[0].parse_status == "no-deadline"
    assert "applicationPages=blocked" in adapter.catalogue_diagnostics
