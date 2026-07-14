from __future__ import annotations

from gradwindow.programme_adapters.bristol import (
    CATALOG_URL,
    BristolAdapter,
    _catalogue_programmes,
)

CATALOGUE = """
<html><body>
  <article class="search-result search-result--course">
    <a href="/study/postgraduate/taught/msc-management/">
      <div class="badge">Taught postgraduate programme</div>
      <h1>MSc Management</h1>
      <dl><dt>Awards available</dt><dd>MSc</dd></dl>
    </a>
  </article>
  <article class="search-result search-result--course">
    <a href="/study/postgraduate/taught/msc-clinical-neuropsychology/">
      <div class="badge">Taught postgraduate programme</div>
      <h1>MSc Clinical Neuropsychology</h1>
      <dl><dt>Awards available</dt><dd>MSc</dd></dl>
    </a>
  </article>
  <article class="search-result search-result--course">
    <a href="/study/postgraduate/taught/msc-health-economics/">
      <div class="badge">Taught postgraduate programme</div>
      <h1>MSc Health Economics</h1>
      <dl><dt>Awards available</dt><dd>MSc, PG Diploma</dd></dl>
    </a>
  </article>
  <article class="search-result search-result--course">
    <a href="/study/postgraduate/taught/pg-diploma-neuropsychology/">
      <div class="badge">Taught postgraduate programme</div>
      <h1>PG Diploma Neuropsychology</h1>
      <dl><dt>Awards available</dt><dd>PG Diploma</dd></dl>
    </a>
  </article>
  <article class="search-result search-result--course">
    <a href="/study/postgraduate/taught-2025/msc-management/">
      <div class="badge">Taught postgraduate programme</div>
      <h1>MSc Management</h1>
      <dl><dt>Awards available</dt><dd>MSc</dd></dl>
    </a>
  </article>
</body></html>
"""

MANAGEMENT = """
<html><head>
  <meta name="faculty" content="Arts Law and Social Sciences">
  <meta name="schools" content="University of Bristol Business School">
</head><body>
  <dl>
    <dt>Start date</dt><dd>September 2026</dd>
    <dt>Application deadline</dt><dd>
      Overseas applicants: 13 August 2026.<br>
      Home applicants: 10 September 2026.<br>
      Places are allocated continuously from September 2025.
    </dd>
  </dl>
</body></html>
"""

MULTIPLE_INTAKES = """
<html><body><dl>
  <dt>Start date</dt><dd>January 2026 September 2026 January 2027</dd>
  <dt>Application deadline</dt><dd>
    For January 2026 start: 11 December 2025.
    For September 2026 start: 10 September 2026.
    For January 2027 start: 5 January 2027.
  </dd>
</dl></body></html>
"""

AWARD_SPECIFIC = """
<html><body><dl>
  <dt>Start date</dt><dd>September 2026</dd>
  <dt>Application deadline</dt><dd>
    For MSc One year full-time on campus:
    Overseas applicants: 13 August 2026. Home applicants: 10 September 2026.
    For all other awards: Application deadline: 31 July 2026.
  </dd>
</dl></body></html>
"""


def test_bristol_adapter_reads_current_masters_and_deadline_variants() -> None:
    adapter = BristolAdapter(minimum_expected_programmes=3, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOGUE
        if url.endswith("/msc-management/"):
            return MANAGEMENT
        if url.endswith("/msc-clinical-neuropsychology/"):
            return MULTIPLE_INTAKES
        if url.endswith("/msc-health-economics/"):
            return AWARD_SPECIFIC
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "bristol-msc-clinical-neuropsychology",
        "bristol-msc-health-economics",
        "bristol-msc-management",
    ]
    management = catalog.programmes[2]
    assert management.faculty == "Arts Law and Social Sciences"
    assert management.department == "University of Bristol Business School"
    assert management.parse_status == "incomplete"
    assert [
        (
            window.round,
            window.applicant_categories,
            window.opens_at,
            window.closes_at,
            window.intake,
        )
        for window in management.windows
    ] == [
        (
            "Overseas applicants",
            ["international"],
            None,
            "2026-08-13",
            "September 2026",
        ),
        (
            "Home applicants",
            ["home"],
            None,
            "2026-09-10",
            "September 2026",
        ),
    ]

    clinical = catalog.programmes[0]
    assert [(window.intake, window.closes_at) for window in clinical.windows] == [
        ("January 2026", "2025-12-11"),
        ("September 2026", "2026-09-10"),
        ("January 2027", "2027-01-05"),
    ]

    health = catalog.programmes[1]
    assert [window.closes_at for window in health.windows] == [
        "2026-08-13",
        "2026-09-10",
    ]


def test_bristol_adapter_keeps_failed_detail_page_without_guessing_dates() -> None:
    adapter = BristolAdapter(minimum_expected_programmes=3, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOGUE
        if url.endswith("/msc-management/"):
            return MANAGEMENT
        if url.endswith("/msc-clinical-neuropsychology/"):
            raise RuntimeError("temporary block")
        if url.endswith("/msc-health-economics/"):
            return "<html><body><p>Applications open in autumn.</p></body></html>"
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)
    failed = catalog.programmes[0]
    no_deadline = catalog.programmes[1]

    assert failed.windows == []
    assert failed.parse_status == "no-deadline"
    assert "temporary block" in failed.deadline_text
    assert no_deadline.windows == []
    assert no_deadline.parse_status == "no-deadline"


def test_bristol_adapter_rejects_implausibly_small_catalogue() -> None:
    adapter = BristolAdapter(minimum_expected_programmes=4, detail_workers=1)

    try:
        adapter.parse_catalog_from_fetcher(lambda _: CATALOGUE)
    except ValueError as exc:
        assert "only contained 3" in str(exc)
    else:
        raise AssertionError("Expected the incomplete catalogue to be rejected")


def test_bristol_catalogue_preserves_existing_conversion_programme_id() -> None:
    catalogue = """
    <article class="search-result search-result--course">
      <a href="/study/postgraduate/taught/msc-computer-science-conversion/">
        <div class="badge">Taught postgraduate programme</div>
        <h1>MSc Computer Science (Conversion)</h1>
        <dl><dt>Awards available</dt><dd>MSc</dd></dl>
      </a>
    </article>
    """

    assert _catalogue_programmes(catalogue)[0].id == (
        "bristol-computer-science-conversion-msc"
    )
