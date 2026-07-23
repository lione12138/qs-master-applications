from __future__ import annotations

import pytest

from gradwindow.programme_adapters.berkeley import CATALOG_URL, BerkeleyAdapter

CATALOG_HTML = """
<main>
  <div class="flyout" id="flyout_40717">
    <div class="flyout__header__text--department">
      <p>Electrical Engineering &amp; Computer Sciences</p>
    </div>
    <div class="flyout__header__text--title">
      <h2>Electrical Engineering &amp; Computer Sciences MEng</h2>
    </div>
    <div class="flyout__header__text--url">
      <a href="https://grad.berkeley.edu/program/electrical-engineering-computer-sciences-meng/">Open</a>
    </div>
    <div class="flyout__body__website">
      <a href="https://eecs.berkeley.edu/academics/graduate/industry-programs/">Visit website</a>
    </div>
    <div class="flyout__body__details--table">
      <div><div><p><strong>Departments</strong></p></div><div><p>Electrical Engineering &amp; Computer Sciences</p></div></div>
      <div><div><p><strong>Application Deadline</strong></p></div><div><p>January 14, 2026</p></div></div>
      <div><div><p><strong>Degrees Awarded</strong></p></div><div><p>Masters / Professional</p></div></div>
      <div><div><p><strong>Admit Terms</strong></p></div><div><p>Fall</p></div></div>
      <div><div><p><strong>Degree Types</strong></p></div><div><p>M.Eng</p></div></div>
    </div>
  </div>
  <div class="flyout" id="flyout_40900">
    <div class="flyout__header__text--department"><p>Design</p></div>
    <div class="flyout__header__text--title"><h2>Design MDes</h2></div>
    <div class="flyout__header__text--url">
      <a href="https://grad.berkeley.edu/program/design-mdes/">Open</a>
    </div>
    <div class="flyout__body__website">
      <a href="https://design.berkeley.edu/">Visit website</a>
    </div>
    <div class="flyout__body__details--table">
      <div><div><p><strong>Departments</strong></p></div><div><p>Design</p></div></div>
      <div><div><p><strong>Application Deadline</strong></p></div><div><p>January 6, 2026</p></div></div>
      <div><div><p><strong>Degrees Awarded</strong></p></div><div><p>Masters / Professional</p></div></div>
      <div><div><p><strong>Admit Terms</strong></p></div><div><p>Fall</p></div></div>
      <div><div><p><strong>Degree Types</strong></p></div><div><p>M.Des.</p></div></div>
    </div>
  </div>
  <div class="flyout" id="flyout_40901">
    <div class="flyout__header__text--department"><p>Information</p></div>
    <div class="flyout__header__text--title"><h2>Information and Data Science MIDS</h2></div>
    <div class="flyout__header__text--url">
      <a href="https://grad.berkeley.edu/program/information-data-science-mids/">Open</a>
    </div>
    <div class="flyout__body__website">
      <a href="https://ischool.berkeley.edu/programs/mids">Visit website</a>
    </div>
    <div class="flyout__body__details--table">
      <div><div><p><strong>Departments</strong></p></div><div><p>Information</p></div></div>
      <div><div><p><strong>Application Deadline</strong></p></div><div><p>See program website</p></div></div>
      <div><div><p><strong>Degrees Awarded</strong></p></div><div><p>Masters / Professional</p></div></div>
      <div><div><p><strong>Admit Terms</strong></p></div><div><p>Spring, Summer, Fall</p></div></div>
      <div><div><p><strong>Degree Types</strong></p></div><div><p>M.I.D.S.</p></div></div>
    </div>
  </div>
  <div class="flyout" id="flyout_20310">
    <div class="flyout__header__text--title"><h2>African American Studies PhD</h2></div>
    <div class="flyout__body__details--table">
      <div><div><p><strong>Degrees Awarded</strong></p></div><div><p>Doctoral / PhD</p></div></div>
      <div><div><p><strong>Application Deadline</strong></p></div><div><p>December 1, 2025</p></div></div>
    </div>
  </div>
</main>
"""


def test_berkeley_adapter_discovers_masters_and_reuses_existing_eecs_id() -> None:
    catalog = BerkeleyAdapter(minimum_expected_programmes=3).parse_catalog(CATALOG_HTML)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "berkeley-eecs-meng",
        "berkeley-40900-design-mdes",
        "berkeley-40901-information-data-science-mids",
    ]
    assert [programme.degree_type for programme in catalog.programmes] == [
        "MEng",
        "MDes",
        "MIDS",
    ]


def test_berkeley_adapter_captures_closing_date_without_inventing_opening() -> None:
    catalog = BerkeleyAdapter(minimum_expected_programmes=3).parse_catalog(CATALOG_HTML)
    by_id = {programme.id: programme for programme in catalog.programmes}
    eecs = by_id["berkeley-eecs-meng"]

    assert eecs.faculty == "Electrical Engineering & Computer Sciences"
    assert eecs.application_url == (
        "https://eecs.berkeley.edu/academics/graduate/industry-programs/meng/"
    )
    assert eecs.windows[0].opens_at is None
    assert eecs.windows[0].closes_at == "2026-01-14"
    assert eecs.windows[0].intake == "Fall admission"
    assert eecs.windows[0].source_url == eecs.source_url
    assert eecs.parse_status == "incomplete"
    assert eecs.retrieval_method == "official-graduate-program-directory"
    assert eecs.evidence_quality == "official-full-text"
    assert "exact application opening date" in eecs.deadline_text

    mids = by_id["berkeley-40901-information-data-science-mids"]
    assert mids.windows == []
    assert mids.parse_status == "no-deadline"
    assert "See program website" in mids.deadline_text


def test_berkeley_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        BerkeleyAdapter(minimum_expected_programmes=4).parse_catalog(CATALOG_HTML)


def test_berkeley_adapter_uses_the_official_graduate_program_directory() -> None:
    assert CATALOG_URL == "https://grad.berkeley.edu/admissions/our-programs/"
