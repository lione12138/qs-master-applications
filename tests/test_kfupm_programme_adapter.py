from __future__ import annotations

import pytest

from gradwindow.programme_adapters.kfupm import (
    CATALOG_URL,
    OPERATIONAL_URL,
    THESIS_CATALOG_URL,
    KFUPMAdapter,
)

PROJECT_HTML = """
<html><body><main>
  <h1>Project-Based Master’s Degrees</h1>
  <h2>Degree list</h2>
  <h5><a href="http://ms.kfupm.edu.sa#master-of-science-in-data-science-&-analytics">
    Master of Science in Data Science &amp; Analytics</a></h5>
  <h5><a href="http://ms.kfupm.edu.sa#master-of-science-in-bioengineering">
    Master of Science in Bioengineering</a></h5>
  <h5><a href="http://ms.kfupm.edu.sa#master-of-computational-material-and-modelling">
    Master of Computational Material and Modelling</a></h5>
</main></body></html>
"""

OPERATIONAL_HTML = """
<html><body>
  <h4>Application Period for Fall 2026 (Third Cycle)</h4>
  <div class="row">
    <div>10 Jun 2026</div><div>Opening Online Application</div>
    <div>11 Jul 2026</div><div>Last Day for submitting Online Application</div>
  </div>
  <div id="programs-acc" class="accordion">
    <div class="accordion-item">
      <h2 id="master-of-science-in-data-science-&amp;-analytics">
        1. Master of Science in Data Science &amp; Analytics
        <span class="badge">CLOSED</span>
      </h2>
      <div><a href="https://nabegh.kfupm.edu.sa/cycle/26/apply">Apply now</a></div>
    </div>
    <div class="accordion-item">
      <h2 id="master-of-science-in-bioengineering">
        2. Master of Science in Bioengineering
      </h2>
      <div><a href="https://nabegh.kfupm.edu.sa/cycle/26/apply">Apply now</a></div>
    </div>
  </div>
</body></html>
"""

THESIS_HTML = """
<html><body><main>
  <h1>Thesis-Based Master’s Degrees and PhD Programs</h1>
  <h2>Degree list</h2>
  <h5><a href="https://bulletin.kfupm.edu.sa/main/program?program_id=1129">
    Executive Master of Business Administration</a></h5>
  <h5><a href="https://bulletin.kfupm.edu.sa/main/program?program_id=142">
    Master of Science in Computer Science</a></h5>
  <h5><a href="https://bulletin.kfupm.edu.sa/main/program?program_id=131">
    Master of Science in Mathematics</a></h5>
  <h5><a href="https://bulletin.kfupm.edu.sa/main/program?program_id=999">
    Doctor of Philosophy in Example</a></h5>
</main></body></html>
"""

PAGES = {
    CATALOG_URL: PROJECT_HTML,
    OPERATIONAL_URL: OPERATIONAL_HTML,
    THESIS_CATALOG_URL: THESIS_HTML,
}


def _adapter() -> KFUPMAdapter:
    return KFUPMAdapter(
        minimum_project_programmes=3,
        maximum_project_programmes=3,
        minimum_thesis_programmes=2,
        maximum_thesis_programmes=2,
        minimum_open_programmes=1,
    )


def test_kfupm_adapter_combines_project_and_thesis_catalogues() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(PAGES.__getitem__)

    assert len(catalog.programmes) == 5
    assert len({item.id for item in catalog.programmes}) == 5
    assert catalog.application_opens_at == "2026-06-10"
    assert {item.department for item in catalog.programmes} == {
        "Project-Based Master's Degrees",
        "Thesis-Based Master's Degrees",
    }
    assert not any("Executive Master" in item.name for item in catalog.programmes)


def test_kfupm_adapter_preserves_existing_data_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(PAGES.__getitem__)
    programme = next(item for item in catalog.programmes if "Data Science" in item.name)

    assert programme.id == "kfupm-data-science-analytics-ms"
    assert programme.windows == []
    assert programme.parse_status == "no-deadline"


def test_kfupm_adapter_maps_window_only_to_open_operational_card() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(PAGES.__getitem__)
    bioengineering = next(
        item for item in catalog.programmes if item.name.endswith("Bioengineering")
    )

    assert bioengineering.application_url == (
        "https://nabegh.kfupm.edu.sa/cycle/26/apply"
    )
    assert [
        (item.round, item.opens_at, item.closes_at) for item in bioengineering.windows
    ] == [("Fall 2026 third cycle", "2026-06-10", "2026-07-11")]
    assert bioengineering.parse_status == "parsed"


def test_kfupm_adapter_keeps_thesis_programmes_in_monitoring() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(PAGES.__getitem__)
    thesis = [item for item in catalog.programmes if "Thesis-Based" in item.department]

    assert len(thesis) == 2
    assert all(item.windows == [] for item in thesis)
    assert all(item.parse_status == "no-deadline" for item in thesis)
    assert all("bulletin.kfupm.edu.sa" in item.source_url for item in thesis)


def test_kfupm_adapter_rejects_truncated_project_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 project-based"):
        KFUPMAdapter(
            minimum_project_programmes=4,
            maximum_project_programmes=5,
            minimum_thesis_programmes=2,
            maximum_thesis_programmes=2,
            minimum_open_programmes=1,
        ).parse_catalog_from_fetcher(PAGES.__getitem__)


def test_kfupm_adapter_rejects_missing_exact_cycle_period() -> None:
    pages = {
        **PAGES,
        OPERATIONAL_URL: "<html><body><h4>Fall 2026 applications</h4></body></html>",
    }

    with pytest.raises(ValueError, match="exact Fall 2026 third-cycle window"):
        _adapter().parse_catalog_from_fetcher(pages.__getitem__)
