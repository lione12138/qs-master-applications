from __future__ import annotations

import pytest

from gradwindow.programme_adapters.cornell import CATALOG_URL, CornellAdapter

CATALOG_HTML = """
<main>
  <div id="programsaztextcontainer" class="page_content tab_content">
    <h2>Programs A-Z</h2>
    <div class="az_sitemap">
      <a href="/programs/aerospace-engineering-meng/">
        Aerospace Engineering (MEng)
      </a>
      <a href="/programs/computer-science-cscn-meng/">
        Computer Science (CSCN-MEng)
      </a>
      <a href="/programs/computer-science-ms/">Computer Science (MS)</a>
      <a href="/programs/management-mps/">Management (MPS)</a>
      <a href="/programs/dual-degree-program-jd-mba/">
        Management and Law (MBA/JD)
      </a>
      <a href="/programs/computer-science-phd/">Computer Science (PhD)</a>
      <a href="/programs/computer-science-bs/">Computer Science (BS)</a>
      <a href="/programs/data-science-minor/">Data Science (Minor)</a>
    </div>
  </div>
  <div id="programsbycollegeschooltextcontainer" class="page_content tab_content">
    <h2>Programs by College/School</h2>
    <h2 class="toggle">Duffield College of Engineering</h2>
    <div class="sitemap">
      <a href="/programs/aerospace-engineering-meng/">
        Aerospace Engineering (MEng)
      </a>
    </div>
    <h2 class="toggle">Bowers College of Computing and Information Science</h2>
    <div class="sitemap">
      <a href="/programs/computer-science-cscn-meng/">
        Computer Science (CSCN-MEng)
      </a>
    </div>
    <h2 class="toggle">Graduate School</h2>
    <div class="sitemap">
      <a href="/programs/computer-science-ms/">Computer Science (MS)</a>
    </div>
    <h2 class="toggle">SC Johnson College of Business</h2>
    <div class="sitemap">
      <a href="/programs/management-mps/">Management (MPS)</a>
      <a href="/programs/dual-degree-program-jd-mba/">
        Management and Law (MBA/JD)
      </a>
    </div>
  </div>
</main>
"""


def test_cornell_adapter_discovers_masters_and_reuses_existing_cs_id() -> None:
    catalog = CornellAdapter(minimum_expected_programmes=5).parse_catalog(CATALOG_HTML)

    assert catalog.application_opens_at is None
    assert [programme.name for programme in catalog.programmes] == [
        "Aerospace Engineering (MEng)",
        "Computer Science (MEng)",
        "Computer Science (MS)",
        "Management (MPS)",
        "Management and Law (MBA/JD)",
    ]
    assert catalog.programmes[1].id == "cornell-computer-science-meng"
    assert catalog.programmes[1].application_url == (
        "https://www.cs.cornell.edu/master-engineering-computer-science/apply"
    )


def test_cornell_adapter_preserves_school_and_monitoring_contract() -> None:
    catalog = CornellAdapter(minimum_expected_programmes=5).parse_catalog(CATALOG_HTML)
    by_name = {programme.name: programme for programme in catalog.programmes}

    aerospace = by_name["Aerospace Engineering (MEng)"]
    assert aerospace.faculty == "Duffield College of Engineering"
    assert aerospace.source_url == (
        "https://catalog.cornell.edu/programs/aerospace-engineering-meng/"
    )
    assert aerospace.application_url == aerospace.source_url
    assert aerospace.windows == []
    assert aerospace.parse_status == "no-deadline"
    assert aerospace.retrieval_method == "official-catalog"
    assert aerospace.evidence_quality == "official-full-text"
    assert "does not state an exact application opening date" in (
        aerospace.deadline_text
    )

    computer_science_ms = by_name["Computer Science (MS)"]
    assert computer_science_ms.faculty == "Graduate School"
    assert computer_science_ms.degree_type == "MS"


def test_cornell_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 5"):
        CornellAdapter(minimum_expected_programmes=6).parse_catalog(CATALOG_HTML)


def test_cornell_adapter_uses_the_official_catalogue() -> None:
    assert CATALOG_URL == "https://catalog.cornell.edu/programs/"
