from __future__ import annotations

from datetime import date

import pytest

from gradwindow.programme_adapters.brown import (
    CATALOG_URL,
    BrownAdapter,
)

CATALOG_HTML = """
<div class="views-row">
  <div class="term-item hidden">Master Program, Professional Education</div>
  <div class="views-field-field-program-degree-type"><div class="field-content">Sc.M.</div></div>
  <h2><a href="/graduate-program/healthcare-leadership-scm">Healthcare Leadership</a></h2>
</div>
<div class="views-row">
  <div class="term-item hidden">Master Program</div>
  <div class="views-field-field-program-degree-type"><div class="field-content">M.Eng., Sc.M.</div></div>
  <h2><a href="/graduate-program/biomedical-engineering-meng-scm">Biomedical Engineering</a></h2>
</div>
<div class="views-row">
  <div class="term-item hidden">Master Program</div>
  <div class="views-field-field-program-degree-type"><div class="field-content">Sc.M.</div></div>
  <h2><a href="/graduate-program/computer-science-scm">Computer Science</a></h2>
</div>
<div class="views-row">
  <div class="term-item hidden">Combined Degree Program, Master Program, Medical Degree</div>
  <div class="views-field-field-program-degree-type"><div class="field-content">M.D., Sc.M.</div></div>
  <h2><a href="/graduate-program/primary-care-population-medicine-program-md-scm">Primary Care-Population Medicine Program</a></h2>
</div>
"""

HEALTHCARE_HTML = """
<main>
  <h1 class="page_title">Healthcare Leadership</h1>
  <ul class="degree_types"><li class="degree_types_title">Sc.M.</li></ul>
  <div class="degrees_info_title"><a class="degrees_info_title_link" href="https://professional.brown.edu/">School of Professional Studies</a></div>
  <div class="section_break_header_container">
    <h2 class="section_break_header_title">Application Information</h2>
    <a class="apply" href="https://apply.professional.brown.edu/portal/app-management">Apply</a>
  </div>
  <div class="typography">
    <p><strong>Summer 2027</strong><br>
      Application Opens: June 16, 2026<br>
      Priority 1 Deadline: October 1, 2026<br>
      Priority 2 Deadline: January 15, 2027<br>
      Final Deadline: March 15, 2027<br>
      *For international applicants, the final deadline to apply is January 15, 2027.
    </p>
    <p><strong>Fall 2027</strong><br>
      Application Opens: September 1, 2026<br>
      Priority 1 Deadline: December 1, 2026<br>
      Priority 2 Deadline: April 1, 2027<br>
      Final Deadline: June 15, 2027<br>
      *For international applicants, the final deadline to apply is May 15, 2027.
    </p>
  </div>
</main>
"""

BIOMEDICAL_HTML = """
<main>
  <h1 class="page_title">Biomedical Engineering</h1>
  <ul class="degree_types">
    <li class="degree_types_title">M.Eng.</li><li class="degree_types_title">Sc.M.</li>
  </ul>
  <div class="degrees_info_title"><a class="degrees_info_title_link" href="https://engineering.brown.edu/">School of Engineering</a></div>
  <div class="section_break_header_container">
    <h2 class="section_break_header_title">Application Information</h2>
    <a class="apply" href="https://apply.professional.brown.edu/portal/app-management">Apply</a>
  </div>
  <div class="typography">
    <h3>Application Deadlines</h3>
    <table>
      <thead><tr><th></th><th>Fifth-Year Students</th><th>International Students</th><th>Final Deadline</th></tr></thead>
      <tbody>
        <tr><th>Fall 2027 Start</th><td>May 1, 2027</td><td>April 1, 2027</td><td>April 15, 2027</td></tr>
      </tbody>
    </table>
  </div>
</main>
"""

COMPUTER_SCIENCE_HTML = """
<main>
  <h1 class="page_title">Computer Science</h1>
  <ul class="degree_types"><li class="degree_types_title">Sc.M.</li></ul>
  <div class="degrees_info_title"><a class="degrees_info_title_link" href="https://cs.brown.edu/">Computer Science</a></div>
  <div class="section_break_header_container">
    <h2 class="section_break_header_title">Application Information</h2>
    <a class="apply" href="https://apply.professional.brown.edu/portal/app-management">Apply</a>
  </div>
  <header><h3 class="secondary_section_break_header_title">Dates/Deadlines</h3></header>
  <div class="date"><h4>Application Deadline</h4><time datetime="2026-01-23T12:00:00Z">January 23, 2026</time></div>
  <div class="date"><h4>5th Year Deadline</h4><time datetime="2026-05-01T12:00:00Z">May 1, 2026</time></div>
</main>
"""


def _url(slug: str) -> str:
    return f"https://graduateprograms.brown.edu/graduate-program/{slug}"


def _fetcher(url: str) -> str:
    pages = {
        CATALOG_URL: CATALOG_HTML,
        _url("healthcare-leadership-scm"): HEALTHCARE_HTML,
        _url("biomedical-engineering-meng-scm"): BIOMEDICAL_HTML,
        _url("computer-science-scm"): COMPUTER_SCIENCE_HTML,
    }
    return pages[url]


def _catalog():
    return BrownAdapter(
        minimum_expected_programmes=4,
        maximum_expected_programmes=4,
        as_of=date(2026, 7, 17),
    ).parse_catalog_from_fetcher(_fetcher)


def test_brown_adapter_discovers_and_splits_official_masters_catalogue() -> None:
    catalog = _catalog()

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "brown-biomedical-engineering-meng",
        "brown-biomedical-engineering-scm",
        "brown-computer-science-scm",
        "brown-healthcare-leadership-scm",
    ]
    assert [programme.degree_type for programme in catalog.programmes] == [
        "MENG",
        "SCM",
        "SCM",
        "SCM",
    ]
    assert all("primary-care" not in item.id for item in catalog.programmes)


def test_brown_adapter_preserves_exact_professional_programme_windows() -> None:
    healthcare = next(
        item
        for item in _catalog().programmes
        if item.id.endswith("healthcare-leadership-scm")
    )

    assert len(healthcare.windows) == 8
    assert healthcare.windows[0].intake == "Fall 2027"
    assert healthcare.windows[0].round == "Priority 1 deadline"
    assert healthcare.windows[0].opens_at == "2026-09-01"
    assert healthcare.windows[0].closes_at == "2026-12-01"
    assert healthcare.windows[-1].intake == "Summer 2027"
    assert healthcare.windows[-1].round == "International final deadline"
    assert healthcare.windows[-1].applicant_categories == ["international-students"]
    assert healthcare.windows[-1].closes_at == "2027-01-15"
    assert healthcare.parse_status == "parsed"
    assert healthcare.faculty == "School of Professional Studies"


def test_brown_adapter_keeps_deadline_only_programmes_in_opening_review() -> None:
    biomedical = [
        item for item in _catalog().programmes if "biomedical-engineering" in item.id
    ]

    assert len(biomedical) == 2
    for programme in biomedical:
        assert programme.parse_status == "incomplete"
        assert [
            (window.round, window.applicant_categories) for window in programme.windows
        ] == [
            ("Final deadline", ["domestic-students"]),
            ("International deadline", ["international-students"]),
        ]
        assert all(window.opens_at is None for window in programme.windows)
        assert "no exact application opening date" in programme.deadline_text


def test_brown_adapter_ignores_expired_and_fifth_year_deadlines() -> None:
    computer_science = next(
        item
        for item in _catalog().programmes
        if item.id == "brown-computer-science-scm"
    )

    assert computer_science.windows == []
    assert computer_science.parse_status == "incomplete"
    assert computer_science.source_url == _url("computer-science-scm")


def test_brown_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 master's programmes"):
        BrownAdapter(
            minimum_expected_programmes=5,
            as_of=date(2026, 7, 17),
        ).parse_catalog_from_fetcher(_fetcher)


def test_brown_adapter_rejects_non_official_catalogue_links() -> None:
    bad_catalogue = CATALOG_HTML.replace(
        "/graduate-program/healthcare-leadership-scm",
        "https://example.com/healthcare-leadership-scm",
    )

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return bad_catalogue
        return _fetcher(url)

    with pytest.raises(ValueError, match="non-official URL"):
        BrownAdapter(
            minimum_expected_programmes=4,
            as_of=date(2026, 7, 17),
        ).parse_catalog_from_fetcher(fetcher)
