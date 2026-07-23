from __future__ import annotations

import pytest

from gradwindow.programme_adapters.uchicago import (
    CATALOG_URL,
    UChicagoAdapter,
    _degree_type,
)

CATALOG_HTML = """
<main>
  <div class="program" data-filter="masters psd">
    <a class="program-name" href="https://datascience.uchicago.edu/education/masters-programs/ms-in-applied-data-science/">Applied Data Science</a>
    <div class="program-details">
      <span class="program-detail"><span class="inline-header">Masters:</span><a href="https://datascience.uchicago.edu/education/masters-programs/ms-in-applied-data-science/">Master of Science</a></span>
      <span class="program-detail"><span class="inline-header">Unit:</span><a href="https://physical-sciences.uchicago.edu/">Physical Sciences</a></span>
    </div>
  </div>
  <div class="program" data-filter="masters phd ssd">
    <a class="program-name" href="https://anthropology.uchicago.edu/">Anthropology</a>
    <div class="program-details">
      <span class="program-detail"><span class="inline-header">Masters:</span><a href="https://mapss.uchicago.edu">Master of Arts Program in the Social Sciences</a></span>
      <span class="program-detail"><span class="inline-header">Unit:</span><a href="https://socialsciences.uchicago.edu/">Social Sciences</a></span>
    </div>
  </div>
  <div class="program" data-filter="masters phd ssd">
    <a class="program-name" href="https://history.uchicago.edu/">History</a>
    <div class="program-details">
      <span class="program-detail"><span class="inline-header">Masters:</span><a href="https://mapss.uchicago.edu/">Master of Arts Program in the Social Sciences</a></span>
      <span class="program-detail"><span class="inline-header">Unit:</span><a href="https://socialsciences.uchicago.edu/">Social Sciences</a></span>
    </div>
  </div>
  <div class="program" data-filter="masters phd booth">
    <a class="program-name" href="https://www.chicagobooth.edu/mba">Business</a>
    <div class="program-details">
      <span class="program-detail"><span class="inline-header">Masters:</span><a href="https://www.chicagobooth.edu/mba">Master of Business Administration</a></span>
      <span class="program-detail"><span class="inline-header">Unit:</span><a href="https://www.chicagobooth.edu/">Booth</a></span>
    </div>
  </div>
  <div class="program" data-filter="masters phd booth">
    <a class="program-name" href="https://www.chicagobooth.edu/master-in-finance">Finance</a>
    <div class="program-details">
      <span class="program-detail"><span class="inline-header">Masters:</span><a href="https://www.chicagobooth.edu/mba">Master of Business Administration</a><a href="https://www.chicagobooth.edu/master-in-finance">Master of Finance</a></span>
      <span class="program-detail"><span class="inline-header">Unit:</span><a href="https://www.chicagobooth.edu/">Booth</a></span>
    </div>
  </div>
  <div class="program" data-filter="phd psd">
    <a class="program-name" href="https://astrophysics.uchicago.edu/">Astronomy and Astrophysics</a>
    <div class="program-details">
      <span class="program-detail"><span class="inline-header">PhD:</span><a href="https://astrophysics.uchicago.edu/">Ph.D.</a></span>
    </div>
  </div>
</main>
"""


def test_uchicago_adapter_deduplicates_shared_masters_and_reuses_ads_id() -> None:
    catalog = UChicagoAdapter(minimum_expected_programmes=4).parse_catalog(CATALOG_HTML)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "uchicago-applied-data-science-ms",
        "uchicago-master-of-arts-program-in-the-social-sciences",
        "uchicago-master-of-business-administration",
        "uchicago-master-of-finance",
    ]
    assert [programme.degree_type for programme in catalog.programmes] == [
        "MS",
        "MA",
        "MBA",
        "MFin",
    ]


def test_uchicago_adapter_preserves_unit_urls_and_monitoring_contract() -> None:
    catalog = UChicagoAdapter(minimum_expected_programmes=4).parse_catalog(CATALOG_HTML)
    by_id = {programme.id: programme for programme in catalog.programmes}
    applied_data_science = by_id["uchicago-applied-data-science-ms"]

    assert applied_data_science.name == "MS in Applied Data Science"
    assert applied_data_science.faculty == "Physical Sciences"
    assert applied_data_science.source_url == (
        "https://datascience.uchicago.edu/education/masters-programs/"
        "ms-in-applied-data-science/"
    )
    assert applied_data_science.application_url == applied_data_science.source_url
    assert applied_data_science.windows == []
    assert applied_data_science.parse_status == "no-deadline"
    assert applied_data_science.retrieval_method == (
        "official-university-graduate-directory"
    )
    assert applied_data_science.evidence_quality == "official-full-text"
    assert "academic units set their own application windows" in (
        applied_data_science.deadline_text
    )
    assert "no dates are inferred" in applied_data_science.deadline_text


def test_uchicago_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 unique master's programmes"):
        UChicagoAdapter(minimum_expected_programmes=5).parse_catalog(CATALOG_HTML)


def test_uchicago_adapter_uses_the_official_graduate_directory() -> None:
    assert CATALOG_URL == "https://grad.uchicago.edu/admissions/programs/"


def test_uchicago_adapter_normalises_the_mpcam_degree_type() -> None:
    assert _degree_type(
        "Master's Program in Computational and Applied Mathematics"
    ) == ("MS")
