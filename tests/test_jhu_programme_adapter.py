from __future__ import annotations

import pytest

from gradwindow.programme_adapters.jhu import CATALOG_URL, JHUAdapter

CATALOG_HTML = """
<main>
  <ul class="program-list">
    <li class="item filter_4 filter_6 filter_17 filter_18 filter_19 filter_24"
        id="isotope-item173">
      <a href="/engineering/engineering-professionals/computer-science/computer-science-master/">
        <span class="title">Computer Science, Master of Science</span>
        <ul class="divisions">
          <li>Whiting School of Engineering (Engineering For Professionals)</li>
        </ul>
        <span class="keyword">Master's</span>
      </a>
    </li>
    <li class="item filter_4 filter_5 filter_15 filter_18" id="isotope-item497">
      <a href="/engineering/full-time-residential-programs/degree-programs/computer-science/computer-science-master-science-engineering/">
        <span class="title">Computer Science, Master of Science in Engineering</span>
        <ul class="divisions">
          <li>Whiting School of Engineering (Full Time, On Campus Programs)</li>
        </ul>
        <span class="keyword">Master's</span>
      </a>
    </li>
    <li class="item filter_4 filter_5 filter_7 filter_18" id="isotope-item221">
      <a href="/public-health/departments/epidemiology/epidemiology-master-health-science/">
        <span class="title">Epidemiology, Master of Health Science</span>
        <ul class="divisions"><li>Bloomberg School of Public Health</li></ul>
        <span class="keyword">Master's</span>
      </a>
    </li>
    <li class="item filter_2 filter_6 filter_7 filter_19" id="isotope-item592">
      <a href="/public-health/certificates/risk-sciences-and-public-policy/">
        <span class="title">Risk Sciences and Public Policy, Certificate</span>
        <ul class="divisions"><li>Bloomberg School of Public Health</li></ul>
      </a>
    </li>
  </ul>
</main>
"""


def test_jhu_adapter_discovers_official_masters_and_reuses_existing_ep_id() -> None:
    catalog = JHUAdapter(minimum_expected_programmes=3).parse_catalog(CATALOG_HTML)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "jhu-engineering-professionals-computer-science-ms",
        "jhu-497-computer-science-master-science-engineering",
        "jhu-221-epidemiology-master-health-science",
    ]
    assert [programme.degree_type for programme in catalog.programmes] == [
        "MS",
        "MSE",
        "MHS",
    ]


def test_jhu_adapter_preserves_division_urls_and_monitoring_contract() -> None:
    catalog = JHUAdapter(minimum_expected_programmes=3).parse_catalog(CATALOG_HTML)
    by_id = {programme.id: programme for programme in catalog.programmes}

    ep_computer_science = by_id["jhu-engineering-professionals-computer-science-ms"]
    assert ep_computer_science.faculty == (
        "Whiting School of Engineering (Engineering For Professionals)"
    )
    assert ep_computer_science.source_url == (
        "https://e-catalogue.jhu.edu/engineering/engineering-professionals/"
        "computer-science/computer-science-master/"
    )
    assert ep_computer_science.application_url == (
        "https://ep.jhu.edu/admissions-aid/admissions/how-to-apply/"
    )
    assert ep_computer_science.windows == []
    assert ep_computer_science.parse_status == "no-deadline"
    assert ep_computer_science.retrieval_method == "official-academic-catalogue"
    assert ep_computer_science.evidence_quality == "official-full-text"
    assert "maintained by its academic divisions" in ep_computer_science.deadline_text
    assert "no dates are inferred" in ep_computer_science.deadline_text


def test_jhu_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        JHUAdapter(minimum_expected_programmes=4).parse_catalog(CATALOG_HTML)


def test_jhu_adapter_uses_the_official_academic_catalogue() -> None:
    assert CATALOG_URL == "https://e-catalogue.jhu.edu/programs/"
