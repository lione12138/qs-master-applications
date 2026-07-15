from __future__ import annotations

from gradwindow.programme_adapters.upenn import (
    CATALOG_URL,
    DESIGN_ADMISSIONS_URL,
    ENGINEERING_ADMISSIONS_URL,
    ENGINEERING_APPLICATION_URL,
    UpennAdapter,
)

CATALOG_HTML = """
<main>
  <a href="/graduate/programs/computer-science-mascs/">
    <span class="title">Computer Science, MASCS</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">School of Engineering and Applied Science</span>
    <span class="keyword">Master's</span>
  </a>
  <a href="/graduate/programs/bioengineering-mse/">
    <span class="title">Bioengineering, MSE</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">School of Engineering and Applied Science</span>
    <span class="keyword">Master's</span>
  </a>
  <a href="/graduate/programs/computer-information-science-mse/">
    <span class="title">Computer &amp; Information Science, MSE</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">School of Engineering and Applied Science</span>
    <span class="keyword">Master's</span>
  </a>
  <a href="/graduate/programs/chemical-biomolecular-engineering-mse/">
    <span class="title">Chemical &amp; Biomolecular Engineering, MSE</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">School of Engineering and Applied Science</span>
  </a>
  <a href="/graduate/programs/social-policy-data-analytics-mssp/">
    <span class="title">Social Policy + Data Analytics, MSSP</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">Certificate</span>
    <span class="keyword">Professional Degree</span>
    <span class="keyword">School of Social Policy &amp; Practice</span>
    <span class="keyword">Master's</span>
  </a>
  <a href="/graduate/programs/architecture-march/">
    <span class="title">Architecture, MArch</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">Stuart Weitzman School of Design</span>
    <span class="keyword">Master's</span>
  </a>
  <a href="/graduate/programs/architecture-ms/">
    <span class="title">Architecture, MS</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">Stuart Weitzman School of Design</span>
    <span class="keyword">Master's</span>
  </a>
  <a href="/graduate/programs/chemistry-phd/">
    <span class="title">Chemistry, PhD</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">School of Arts &amp; Sciences</span>
    <span class="keyword">PhD</span>
  </a>
  <a href="/graduate/programs/data-science-certificate/">
    <span class="title">Data Science, Certificate</span>
    <span class="keyword">Graduate</span>
    <span class="keyword">School of Engineering and Applied Science</span>
    <span class="keyword">Certificate</span>
  </a>
</main>
"""

ENGINEERING_HTML = """
<section id="programs">
  <article class="program">
    <h2>Bioengineering, MSE</h2>
    <h3>Application Dates</h3>
    <p>Application Opens: September 15, 2025</p>
    <p>Deadline: February 1, 2026</p>
  </article>
  <article class="program">
    <h2>Computer &amp; Information Science, MSE</h2>
    <h3>Application Dates</h3>
    <p>Application Opens: September 15, 2025</p>
    <p>Early Application Deadline: November 1, 2025</p>
    <p>Regular Application Deadline: February 1, 2026</p>
  </article>
  <article class="program">
    <h2>Chemical &amp; Biomolecular Engineering, MSE</h2>
    <p>Application Opens: September 15, 2025</p>
    <p>Deadline: February 1, 2026</p>
  </article>
  <article class="program">
    <h2>Applied Science in Computer Science, MAS-CS</h2>
    <p>Application Opens: Fall 2026</p>
  </article>
</section>
"""

DESIGN_HTML = """
<main>
  <h1>Fall 2026 Online Application, Deadlines, and Fee</h1>
  <ul>
    <li>December 10, 2025: MS in Architecture</li>
    <li>January 7, 2026: Master of Architecture (M.Arch), MSD in Advanced
      Architectural Design, and Master in Environmental Building Design</li>
    <li>January 14, 2026: Master of City Planning, Master of Landscape
      Architecture, Master of Fine Arts, and Master of Urban Spatial Analytics</li>
  </ul>
</main>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url == ENGINEERING_ADMISSIONS_URL:
        return ENGINEERING_HTML
    if url == DESIGN_ADMISSIONS_URL:
        return DESIGN_HTML
    raise AssertionError(url)


def test_upenn_adapter_recovers_mislabeled_masters_and_ignores_other_degrees() -> None:
    catalog = UpennAdapter(minimum_expected_programmes=7).parse_catalog_from_fetcher(
        _fetcher
    )

    assert len(catalog.programmes) == 7
    assert [programme.name for programme in catalog.programmes] == [
        "Applied Science in Computer Science, MAS-CS",
        "Architecture, MArch",
        "Architecture, MS",
        "Bioengineering, MSE",
        "Chemical & Biomolecular Engineering, MSE",
        "Computer & Information Science, MSE",
        "Social Policy + Data Analytics, MSSP",
    ]
    chemical = catalog.programmes[4]
    assert chemical.faculty == "School of Engineering and Applied Science"
    social_policy = catalog.programmes[6]
    assert social_policy.faculty == "School of Social Policy & Practice"
    assert social_policy.source_url.endswith(
        "/graduate/programs/social-policy-data-analytics-mssp/"
    )


def test_upenn_adapter_parses_only_fully_explicit_engineering_windows() -> None:
    catalog = UpennAdapter(minimum_expected_programmes=7).parse_catalog_from_fetcher(
        _fetcher
    )
    by_name = {programme.name: programme for programme in catalog.programmes}

    bioengineering = by_name["Bioengineering, MSE"]
    assert bioengineering.application_url == ENGINEERING_APPLICATION_URL
    assert bioengineering.parse_status == "parsed"
    assert [
        (window.round, window.intake, window.opens_at, window.closes_at)
        for window in bioengineering.windows
    ] == [("Regular admissions", "Fall 2026", "2025-09-15", "2026-02-01")]

    computer_science = by_name["Computer & Information Science, MSE"]
    assert [
        (window.round, window.opens_at, window.closes_at)
        for window in computer_science.windows
    ] == [
        ("Early admissions", "2025-09-15", "2025-11-01"),
        ("Regular admissions", "2025-09-15", "2026-02-01"),
    ]

    existing = by_name["Applied Science in Computer Science, MAS-CS"]
    assert existing.id == "penn-applied-science-computer-science-mas"
    assert existing.windows == []
    assert existing.parse_status == "no-deadline"

    social_policy = by_name["Social Policy + Data Analytics, MSSP"]
    assert social_policy.windows == []
    assert social_policy.parse_status == "no-deadline"

    architecture = by_name["Architecture, MArch"]
    assert architecture.parse_status == "incomplete"
    assert [(window.opens_at, window.closes_at) for window in architecture.windows] == [
        (None, "2026-01-07")
    ]
    architecture_ms = by_name["Architecture, MS"]
    assert [
        (window.opens_at, window.closes_at) for window in architecture_ms.windows
    ] == [(None, "2025-12-10")]


def test_upenn_adapter_rejects_a_truncated_catalogue() -> None:
    try:
        UpennAdapter(minimum_expected_programmes=8).parse_catalog_from_fetcher(_fetcher)
    except ValueError as exc:
        assert "only contained 7" in str(exc)
    else:
        raise AssertionError("Truncated Penn catalogue was accepted")
