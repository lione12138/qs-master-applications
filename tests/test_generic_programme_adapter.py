from __future__ import annotations

from gradwindow.programme_adapters.generic import (
    GenericProgrammeAdapter,
    GenericProgrammeConfig,
)

CATALOG_HTML = """
<html>
  <head><title>Graduate programmes</title></head>
  <body>
    <a href="/study/postgraduate/master-of-computer-science">
      Master of Computer Science
    </a>
    <a href="/study/postgraduate/msc-data-science">MSc Data Science</a>
    <a href="/study/postgraduate/master-of-stale-page">Master of Stale Page</a>
    <a href="/study/undergraduate/bachelor-of-science">Bachelor of Science</a>
    <a href="/study/masters/admissions">Master's admissions</a>
    <a href="/study/masters/programs">Master's Programs</a>
    <a href="/people/jane-doe">Jane Doe, MEd</a>
    <a href="/study/masters/fees-and-funding">Master's fees and funding</a>
    <a href="https://example.net/study/postgraduate/master-of-finance">
      Master of Finance
    </a>
  </body>
</html>
"""

COMPUTER_SCIENCE_HTML = """
<html>
  <body>
    <h1>Master of Computer Science</h1>
    <p>
      The application portal opens September 1, 2026.
      Application deadline: January 14, 2027.
    </p>
  </body>
</html>
"""

DATA_SCIENCE_HTML = """
<html>
  <body>
    <h1>MSc Data Science</h1>
    <p>Applications for the next intake are coming soon.</p>
  </body>
</html>
"""


def test_generic_adapter_follows_official_masters_links_and_extracts_dates() -> None:
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id="example-university",
            school_prefix="example",
            seed_urls=("https://example.edu/graduate/programmes",),
            official_domains=("example.edu",),
            default_application_url="https://example.edu/apply",
            default_intake="Fall 2027",
            minimum_expected_programmes=2,
        )
    )
    pages = {
        "https://example.edu/graduate/programmes": CATALOG_HTML,
        "https://example.edu/study/postgraduate/master-of-computer-science": (
            COMPUTER_SCIENCE_HTML
        ),
        "https://example.edu/study/postgraduate/msc-data-science": DATA_SCIENCE_HTML,
    }

    def fetcher(url: str) -> str:
        if url.endswith("/master-of-stale-page"):
            raise RuntimeError("HTTP 404")
        return pages[url]

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert [programme.id for programme in catalog.programmes] == [
        "example-master-of-computer-science",
        "example-msc-data-science",
    ]
    computer_science = catalog.programmes[0]
    assert computer_science.parse_status == "parsed"
    assert [
        (window.round, window.opens_at, window.closes_at)
        for window in computer_science.windows
    ] == [("Application deadline", "2026-09-01", "2027-01-14")]
    assert computer_science.windows[0].intake == "Fall 2027"
    assert catalog.programmes[1].parse_status == "no-deadline"


def test_generic_adapter_uses_configured_opening_date_when_page_only_has_deadline() -> (
    None
):
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id="example-university",
            school_prefix="example",
            seed_urls=("https://example.edu/graduate/programmes",),
            official_domains=("example.edu",),
            default_application_url="https://example.edu/apply",
            default_application_opens_at="2026-09-01",
            minimum_expected_programmes=1,
            max_detail_pages=1,
        )
    )
    detail_html = """
    <html><body>
      <h1>Master of Computer Science</h1>
      <p>Application deadline: January 14, 2027.</p>
    </body></html>
    """
    pages = {
        "https://example.edu/graduate/programmes": CATALOG_HTML,
        "https://example.edu/study/postgraduate/master-of-computer-science": detail_html,
    }

    catalog = adapter.parse_catalog_from_fetcher(lambda url: pages[url])

    assert catalog.application_opens_at == "2026-09-01"
    assert catalog.programmes[0].parse_status == "parsed"
    assert catalog.programmes[0].windows[0].opens_at is None


def test_generic_adapter_does_not_treat_open_days_as_application_opening_dates() -> (
    None
):
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id="example-university",
            school_prefix="example",
            seed_urls=("https://example.edu/graduate/programmes",),
            official_domains=("example.edu",),
            default_application_url="https://example.edu/apply",
            minimum_expected_programmes=1,
            max_detail_pages=1,
        )
    )
    detail_html = """
    <html><body>
      <h1>Master of Computer Science</h1>
      <p>
        Join our postgraduate open day on 31 July 2026.
        Application deadline: 28 August 2026.
      </p>
    </body></html>
    """
    pages = {
        "https://example.edu/graduate/programmes": CATALOG_HTML,
        "https://example.edu/study/postgraduate/master-of-computer-science": detail_html,
    }

    catalog = adapter.parse_catalog_from_fetcher(lambda url: pages[url])

    assert catalog.programmes[0].parse_status == "incomplete"
    assert [
        (window.opens_at, window.closes_at) for window in catalog.programmes[0].windows
    ] == [(None, "2026-08-28")]


def test_generic_adapter_ignores_scholarship_application_deadlines() -> None:
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id="example-university",
            school_prefix="example",
            seed_urls=("https://example.edu/graduate/programmes",),
            official_domains=("example.edu",),
            default_application_url="https://example.edu/apply",
            minimum_expected_programmes=1,
            max_detail_pages=1,
        )
    )
    detail_html = """
    <html><body>
      <h1>Master of Computer Science</h1>
      <p>
        Scholarship information: £3,000 tuition fee discount.
        Application deadline: 31 July 2026.
      </p>
    </body></html>
    """
    pages = {
        "https://example.edu/graduate/programmes": CATALOG_HTML,
        "https://example.edu/study/postgraduate/master-of-computer-science": detail_html,
    }

    catalog = adapter.parse_catalog_from_fetcher(lambda url: pages[url])

    assert catalog.programmes[0].parse_status == "no-deadline"
    assert catalog.programmes[0].windows == []


def test_generic_adapter_uses_configured_school_deadline_when_page_has_apply_status() -> (
    None
):
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id="example-university",
            school_prefix="example",
            seed_urls=("https://example.edu/graduate/programmes",),
            official_domains=("example.edu",),
            default_application_url="https://example.edu/apply",
            default_intake="September 2026",
            default_application_opens_at="2025-09-15",
            default_application_closes_at="2026-09-04",
            default_deadline_evidence=(
                "Applications open 15 September 2025 and close 4 September 2026."
            ),
            minimum_expected_programmes=1,
            max_detail_pages=1,
        )
    )
    detail_html = """
    <html><body>
      <h1>Master of Computer Science</h1>
      <p>Apply now for 2026 entry.</p>
    </body></html>
    """
    pages = {
        "https://example.edu/graduate/programmes": CATALOG_HTML,
        "https://example.edu/study/postgraduate/master-of-computer-science": detail_html,
    }

    catalog = adapter.parse_catalog_from_fetcher(lambda url: pages[url])

    assert catalog.application_opens_at == "2025-09-15"
    assert catalog.programmes[0].parse_status == "parsed"
    assert [
        (window.round, window.opens_at, window.closes_at, window.intake)
        for window in catalog.programmes[0].windows
    ] == [("Application deadline", None, "2026-09-04", "September 2026")]
    assert "4 September 2026" in catalog.programmes[0].deadline_text


def test_generic_adapter_labels_applicant_specific_deadlines_and_ignores_old_dates() -> (
    None
):
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id="example-university",
            school_prefix="example",
            seed_urls=("https://example.edu/graduate/programmes",),
            official_domains=("example.edu",),
            default_application_url="https://example.edu/apply",
            minimum_expected_programmes=1,
            max_detail_pages=1,
        )
    )
    detail_html = """
    <html><body>
      <h1>Master of Computer Science</h1>
      <p>
        Application deadline Overseas applicants: 13 August 2026.
        Home applicants: 10 September 2026.
        Recognition rules changed from 1 January 2021.
      </p>
    </body></html>
    """
    pages = {
        "https://example.edu/graduate/programmes": CATALOG_HTML,
        "https://example.edu/study/postgraduate/master-of-computer-science": detail_html,
    }

    catalog = adapter.parse_catalog_from_fetcher(lambda url: pages[url])

    assert [
        (window.round, window.applicant_categories, window.closes_at)
        for window in catalog.programmes[0].windows
    ] == [
        ("Overseas applicants", ["international-students"], "2026-08-13"),
        ("Home applicants", ["domestic-students"], "2026-09-10"),
    ]


def test_generic_adapter_can_follow_how_to_apply_links_for_deadlines() -> None:
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id="example-university",
            school_prefix="example",
            seed_urls=("https://example.edu/graduate/programmes",),
            official_domains=("example.edu",),
            default_application_url="https://example.edu/apply",
            minimum_expected_programmes=1,
            max_detail_pages=1,
            follow_application_links=True,
        )
    )
    detail_html = """
    <html><body>
      <h1>MS in Data Science</h1>
      <a href="/how-to-apply/">How to Apply</a>
    </body></html>
    """
    how_to_apply_html = """
    <html><body>
      <h1>How to Apply</h1>
      <p>
        Application deadlines for Fall 2027:
        PhD in Data Science – December 16, 2026.
        MS in Data Science (MSDS) – January 29, 2027.
      </p>
    </body></html>
    """
    pages = {
        "https://example.edu/graduate/programmes": (
            '<a href="/study/postgraduate/ms-data-science">MS in Data Science</a>'
        ),
        "https://example.edu/study/postgraduate/ms-data-science": detail_html,
        "https://example.edu/how-to-apply/": how_to_apply_html,
    }

    catalog = adapter.parse_catalog_from_fetcher(lambda url: pages[url])

    assert catalog.programmes[0].parse_status == "incomplete"
    assert [
        (window.round, window.opens_at, window.closes_at)
        for window in catalog.programmes[0].windows
    ] == [("Application deadline", None, "2027-01-29")]
