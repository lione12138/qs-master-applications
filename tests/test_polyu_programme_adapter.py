from __future__ import annotations

from gradwindow.programme_adapters.polyu import PolyUAdapter

POLYU_HTML = """
<html><body>
  <div class="swiper-slide event">
    <img alt="Application Starts" />
    <div class="event-date" data-start-date="2026-07-02"></div>
  </div>
  <a class="programme" href="/study/pg/tpg/2027/61030-fit-pit">
    <div class="programmes-code-and-entry-description">61030 | Sept 2027 Entry</div>
    <div class="title">Information Technology - MSc - Master of Science</div>
    <div class="deadline-section">
      <div>Local Application Deadline: 20 Oct 2026 (Early Round)</div>
      <div>Non-Local Application Deadline: 25 Feb 2027 (Main Round)</div>
    </div>
  </a>
  <a class="programme" href="/study/pg/tpg/2027/02018">
    <div class="programmes-code-and-entry-description">02018 | Sept 2027 Entry</div>
    <div class="title">Management - Doctor - Doctor</div>
  </a>
</body></html>
"""


def test_polyu_adapter_extracts_master_programmes_and_deadlines() -> None:
    catalog = PolyUAdapter(minimum_expected_programmes=1).parse_catalog(POLYU_HTML)

    assert catalog.application_opens_at == "2026-07-02"
    assert len(catalog.programmes) == 1
    programme = catalog.programmes[0]
    assert programme.id == "polyu-information-technology-msc"
    assert programme.name == "MSc in Information Technology"
    assert programme.source_url.endswith("/study/pg/tpg/2027/61030-fit-pit")
    assert [
        (item.round, item.applicant_categories, item.closes_at)
        for item in programme.windows
    ] == [
        ("Early round", ["domestic-students"], "2026-10-20"),
        ("Main round", ["international-students"], "2027-02-25"),
    ]
