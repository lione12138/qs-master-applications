from __future__ import annotations

from gradwindow.programme_adapters.southampton import (
    CATALOG_URL,
    SouthamptonAdapter,
)

CATALOGUE_HTML = """
<html><body><ul>
  <li class="course-list-item" data-study-level="pg_course">
    <a href="/courses/data-science-masters-msc">
      <div class="leading-none text-black font-semibold">MSc</div>
      <h3 class="card-title">Data Science</h3>
    </a>
  </li>
  <li class="course-list-item" data-study-level="pg_course">
    <a href="/courses/cultural-studies-masters-ma">
      <div class="leading-none text-black font-semibold">MA</div>
      <h3 class="card-title">Cultural Studies</h3>
    </a>
  </li>
  <li class="course-list-item" data-study-level="pg_course">
    <a href="/courses/nursing-adult-masters-msc">
      <div class="leading-none text-black font-semibold">MSc</div>
      <h3 class="card-title">Nursing (Adult)</h3>
    </a>
  </li>
  <li class="course-list-item" data-study-level="pg_course">
    <a href="/courses/online-teaching-masters-pgcert">
      <div class="leading-none text-black font-semibold">PGCert</div>
      <h3 class="card-title">Online Teaching</h3>
    </a>
  </li>
  <li class="course-list-item" data-study-level="ug_course_v1">
    <a href="/courses/biology-degree-msci">
      <div class="leading-none text-black font-semibold">MSci</div>
      <h3 class="card-title">Biology</h3>
    </a>
  </li>
</ul></body></html>
"""

DATA_SCIENCE_HTML = """
<html><body>
  <h1>Data Science (MSc)</h1>
  <div>Next course starts <strong>September 2026</strong></div>
  <div class="copy">
    <h3>Application deadlines</h3>
    <section><h4>UK students</h4>
      <p>The deadline to apply for this course is Wednesday 2 September 2026,
      midday UK time.</p>
    </section>
    <section><h4>International students</h4>
      <p>The deadline to apply for this course is Wednesday 19 August 2026,
      midday UK time.</p>
    </section>
  </div>
</body></html>
"""

CULTURAL_STUDIES_HTML = """
<html><body>
  <h1>Cultural Studies (MA)</h1>
  <div>Next course starts September 2026</div>
  <div class="copy">
    <h3>Application deadlines</h3>
    <p>There are different application deadlines for this course.</p>
    <ul>
      <li>International applicants: Wednesday 26 August 2026, midday UK time</li>
      <li>UK applicants: Wednesday 9 September 2026, midday UK time</li>
    </ul>
    <p>Applications for this course are open, so you can apply now.</p>
  </div>
</body></html>
"""

NURSING_HTML = """
<html><body>
  <h1>Nursing (Adult) (MSc)</h1>
  <div>Next course starts September 2026</div>
  <div class="copy">
    <h3>Application deadlines</h3>
    <p>All applications submitted by Tuesday 30th June 2026 are guaranteed
    consideration.</p>
  </div>
</body></html>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOGUE_HTML
    if url.endswith("/data-science-masters-msc"):
        return DATA_SCIENCE_HTML
    if url.endswith("/cultural-studies-masters-ma"):
        return CULTURAL_STUDIES_HTML
    if url.endswith("/nursing-adult-masters-msc"):
        return NURSING_HTML
    raise AssertionError(url)


def test_southampton_adapter_parses_catalogue_and_applicant_deadlines() -> None:
    catalog = SouthamptonAdapter(
        minimum_expected_programmes=3,
        detail_workers=2,
    ).parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "southampton-cultural-studies-ma",
        "southampton-data-science-msc",
        "southampton-nursing-adult-msc",
    ]
    data_science = catalog.programmes[1]
    assert data_science.name == "Data Science (MSc)"
    assert data_science.parse_status == "incomplete"
    assert [
        (
            window.applicant_categories,
            window.opens_at,
            window.closes_at,
            window.intake,
        )
        for window in data_science.windows
    ] == [
        (["domestic-students"], None, "2026-09-02", "September 2026"),
        (["international-students"], None, "2026-08-19", "September 2026"),
    ]
    cultural_studies = catalog.programmes[0]
    assert [window.closes_at for window in cultural_studies.windows] == [
        "2026-09-09",
        "2026-08-26",
    ]
    assert "Applications for this course are open" in cultural_studies.deadline_text
    nursing = catalog.programmes[2]
    assert [
        (window.closes_at, window.applicant_categories) for window in nursing.windows
    ] == [("2026-06-30", ["all"])]


def test_southampton_adapter_rejects_incomplete_catalogue() -> None:
    adapter = SouthamptonAdapter(minimum_expected_programmes=4)

    try:
        adapter.parse_catalog_from_fetcher(_fetcher)
    except ValueError as exc:
        assert "only contained 3" in str(exc)
    else:
        raise AssertionError("Incomplete Southampton catalogue was accepted")
