from __future__ import annotations

import pytest

from gradwindow.programme_adapters.epfl import (
    ADMISSIONS_URL,
    CATALOG_URL,
    EPFLAdapter,
)

CATALOG_HTML = """
<main>
  <h4>School of Computer and Communication Sciences</h4>
  <div class="container-full">
    <a class="card card-overlay" href="https://www.epfl.ch/education/master/programs/computer-science/">
      <h3 class="card-title"><span>Computer Science</span></h3>
    </a>
    <a class="card card-overlay" href="https://www.epfl.ch/education/master/programs/cyber-security/">
      <h3 class="card-title"><span>Cyber Security</span></h3>
    </a>
  </div>
  <h4>College of Humanities</h4>
  <div class="container-full">
    <a class="card card-overlay" href="https://www.epfl.ch/education/master/programs/digital-humanities/">
      <h3 class="card-title"><span>Digital Humanities</span></h3>
    </a>
  </div>
</main>
"""

ADMISSIONS_HTML = """
<main>
  <h2>Important deadlines</h2>
  <p>
    Applications can be filled online from mid-November to the 15th of
    December, or from the 16th of December to the 31st of March.
  </p>
  <p>
    Regardless of which deadline you choose to meet, studies begin in early
    September, following acceptance.
  </p>
</main>
"""


def test_epfl_adapter_discovers_masters_and_reuses_existing_cs_id() -> None:
    catalog = EPFLAdapter(minimum_expected_programmes=3).parse_pages(
        catalog_html=CATALOG_HTML,
        admissions_html=ADMISSIONS_HTML,
    )

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "epfl-computer-science-msc",
        "epfl-cyber-security-master",
        "epfl-digital-humanities-master",
    ]
    assert all(programme.degree_type == "MSc" for programme in catalog.programmes)


def test_epfl_adapter_preserves_faculty_urls_and_yearless_policy() -> None:
    catalog = EPFLAdapter(minimum_expected_programmes=3).parse_pages(
        catalog_html=CATALOG_HTML,
        admissions_html=ADMISSIONS_HTML,
    )
    computer_science = catalog.programmes[0]

    assert computer_science.faculty == ("School of Computer and Communication Sciences")
    assert computer_science.source_url == (
        "https://www.epfl.ch/education/master/programs/computer-science/"
    )
    assert computer_science.application_url == (
        "https://www.epfl.ch/education/admission/admission-2/"
        "master-admission-criteria-application/online-application/"
    )
    assert computer_science.windows == []
    assert computer_science.parse_status == "no-deadline"
    assert computer_science.retrieval_method == (
        "official-master-directory-and-admissions-policy"
    )
    assert computer_science.evidence_quality == "official-full-text"
    assert "does not publish the cycle year" in computer_science.deadline_text
    assert "16 December to 31 March" in computer_science.deadline_text
    assert "no dates are inferred" in computer_science.deadline_text


def test_epfl_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        EPFLAdapter(minimum_expected_programmes=4).parse_pages(
            catalog_html=CATALOG_HTML,
            admissions_html=ADMISSIONS_HTML,
        )


def test_epfl_adapter_rejects_changed_deadline_policy() -> None:
    with pytest.raises(ValueError, match="current yearless application rounds"):
        EPFLAdapter(minimum_expected_programmes=3).parse_pages(
            catalog_html=CATALOG_HTML,
            admissions_html="<p>Applications open later.</p>",
        )


def test_epfl_adapter_uses_official_master_and_admissions_pages() -> None:
    assert CATALOG_URL == "https://www.epfl.ch/education/master/programs/"
    assert ADMISSIONS_URL == (
        "https://www.epfl.ch/education/admission/admission-2/"
        "master-admission-criteria-application/"
    )
