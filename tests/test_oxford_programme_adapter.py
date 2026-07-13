from __future__ import annotations

import pytest

from gradwindow.programme_adapters.oxford import OxfordAdapter

OXFORD_PAGE = """
<html><body>
  <div class="view-content">
    <div class="views-row">
      <h3><a href="/admissions/graduate/courses/msc-advanced-computer-science">Advanced Computer Science</a> MSc</h3>
      <div class="course-department">Computer Science</div>
      <div>Full time</div><div>12 months</div>
    </div>
    <div class="views-row">
      <h3><a href="/admissions/graduate/courses/mphil-economics">Economics</a> MPhil</h3>
      <div class="course-department">Economics</div>
      <div>Full time</div><div>21 months</div>
    </div>
    <div class="views-row">
      <h3><a href="/admissions/graduate/courses/msc-earth-sciences-research">Earth Sciences</a> MSc by Research</h3>
      <div class="course-department">Earth Sciences</div>
    </div>
    <div class="views-row">
      <h3><a href="/admissions/graduate/courses/mphil-law">Law</a> MPhil</h3>
      <div class="course-department">Law</div>
    </div>
    <a href="https://third-party.example/msc-data-science">Data Science MSc</a>
  </div>
</body></html>
"""

OXFORD_DETAIL = """
<html><body>
  <h1>MSc in Advanced Computer Science</h1>
  <div>Expected start date October 2027</div>
  <section>
    <h2>Application deadlines</h2>
    <p>12:00 midday UK time on:</p>
    <ul>
      <li>Tuesday 2 December 2026</li>
      <li>Wednesday 6 January 2027</li>
    </ul>
  </section>
</body></html>
"""


def test_oxford_adapter_keeps_taught_masters_and_excludes_research_degrees() -> None:
    catalog = OxfordAdapter(minimum_expected_programmes=2).parse_catalog(OXFORD_PAGE)

    assert [item.id for item in catalog.programmes] == [
        "oxford-advanced-computer-science-msc",
        "oxford-economics-mphil",
    ]
    assert catalog.programmes[0].name == "MSc in Advanced Computer Science"
    assert catalog.programmes[0].faculty == "Computer Science"
    assert catalog.programmes[0].parse_status == "no-deadline"


def test_oxford_adapter_fetches_pagination_and_parses_deadline_stages() -> None:
    first_page = OXFORD_PAGE.replace(
        "</body>", '<nav><a href="?page=1">Next</a></nav></body>'
    )
    second_page = OXFORD_PAGE.replace(
        "Advanced Computer Science", "Mathematical and Computational Finance"
    ).replace("msc-advanced-computer-science", "msc-mathematical-computational-finance")

    def fetcher(url: str) -> str:
        if "/courses/msc-" in url:
            return OXFORD_DETAIL
        if "/courses/mphil-" in url:
            return "<h1>MPhil in Economics</h1><p>Closed to applications for entry in 2026-27. Register to receive an email when applications open (for entry in 2027-28).</p>"
        return second_page if "page=1" in url else first_page

    catalog = OxfordAdapter(
        minimum_expected_programmes=3,
        detail_workers=1,
    ).parse_catalog_from_fetcher(fetcher)

    assert len(catalog.programmes) == 3
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "oxford-advanced-computer-science-msc"
    )
    assert programme.name == "MSc in Advanced Computer Science"
    assert programme.parse_status == "incomplete"
    assert [
        (window.round, window.opens_at, window.closes_at, window.intake)
        for window in programme.windows
    ] == [
        ("Application deadline 1", None, "2026-12-02", "October 2027"),
        ("Application deadline 2", None, "2027-01-06", "October 2027"),
    ]
    economics = next(
        item for item in catalog.programmes if item.id == "oxford-economics-mphil"
    )
    assert economics.windows == []
    assert "2027-28" in economics.deadline_text


def test_oxford_adapter_rejects_partial_catalogues() -> None:
    with pytest.raises(ValueError, match="expected at least 3"):
        OxfordAdapter(minimum_expected_programmes=3).parse_catalog(OXFORD_PAGE)
