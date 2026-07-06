from __future__ import annotations

import pytest

from gradwindow.programme_adapters.imperial import ImperialAdapter

CATALOG_PAGE_1 = """
<html><body>
  <div class="course-card">
    <ul class="course-tags-list">
      <li class="course-tags-list__type">Postgraduate taught</li>
      <li class="course-tags-list__qualification">MSc</li>
    </ul>
    <h4 class="course-card__title">
      <a href="/study/courses/postgraduate-taught/2026/advanced-chemical-engineering/">
        Advanced Chemical Engineering
      </a>
    </h4>
  </div>
  <nav class="pagination">
    <a href="/study/courses/postgraduate-taught/?page=2">2</a>
  </nav>
</body></html>
"""

CATALOG_PAGE_2 = """
<html><body>
  <div class="course-card">
    <ul class="course-tags-list">
      <li class="course-tags-list__qualification">MSc</li>
    </ul>
    <h4 class="course-card__title">
      <a href="/study/courses/postgraduate-taught/2026/advanced-computing/">
        Advanced Computing
      </a>
    </h4>
  </div>
</body></html>
"""

ROUNDS_DETAIL = """
<html><body>
  <section class="course-key-facts__data">
    <ul class="course-key-facts__items">
      <li><h3>Qualification</h3><h4>MSc</h4></li>
      <li><h3>Start date</h3><h4>September 2026</h4></li>
      <li><h3>Delivered by</h3>
        <ul><li><h4>Department of Chemical Engineering</h4></li></ul>
      </li>
    </ul>
  </section>
  <h2>How to apply</h2>
  <h3>Apply online</h3>
  <p>You can submit one application form per year of entry.</p>
  <a href="https://myimperial.powerappsportals.com/">Apply now</a>
  <h3>Application rounds</h3>
  <div>
    <p>We operate a staged admissions process.</p>
    <h4>Round 1</h4>
    <p>Business School courses only.</p>
    <h4>Round 2</h4>
    <ul><li>Applications open on Monday 29 September 2025</li>
      <li>Applications close on Wednesday 7 January 2026</li></ul>
    <h4>Round 3</h4>
    <ul><li>Applications open on Thursday 8 January 2026</li>
      <li>Applications close on Wednesday 11 March 2026</li></ul>
  </div>
</body></html>
"""

NO_ROUNDS_DETAIL = """
<html><body>
  <section class="course-key-facts__data">
    <ul class="course-key-facts__items">
      <li><h3>Start date</h3><h4>September 2026</h4></li>
      <li><h3>Delivered by</h3><h4>Department of Computing</h4></li>
    </ul>
  </section>
  <h2>How to apply</h2>
  <p>You can choose up to two courses.</p>
  <a href="https://myimperial.powerappsportals.com/">Apply now</a>
</body></html>
"""


def test_imperial_adapter_extracts_paginated_catalog_and_rounds() -> None:
    def fetcher(url: str) -> str:
        if "page=2" in url:
            return CATALOG_PAGE_2
        if url.endswith("/advanced-chemical-engineering/"):
            return ROUNDS_DETAIL
        if url.endswith("/advanced-computing/"):
            return NO_ROUNDS_DETAIL
        return CATALOG_PAGE_1

    catalog = ImperialAdapter(
        minimum_expected_programmes=2,
        detail_workers=1,
    ).parse_catalog_from_fetcher(fetcher)

    assert [item.id for item in catalog.programmes] == [
        "imperial-advanced-chemical-engineering-msc",
        "imperial-advanced-computing-msc",
    ]
    chemical = catalog.programmes[0]
    assert chemical.name == "MSc Advanced Chemical Engineering"
    assert chemical.department == "Department of Chemical Engineering"
    assert chemical.application_url == "https://myimperial.powerappsportals.com/"
    assert [
        (window.round, window.opens_at, window.closes_at, window.intake)
        for window in chemical.windows
    ] == [
        ("Round 2", "2025-09-29", "2026-01-07", "September 2026"),
        ("Round 3", "2026-01-08", "2026-03-11", "September 2026"),
    ]
    assert chemical.parse_status == "parsed"

    computing = catalog.programmes[1]
    assert computing.department == "Department of Computing"
    assert computing.windows == []
    assert computing.parse_status == "no-deadline"


def test_imperial_adapter_rejects_missing_cards() -> None:
    with pytest.raises(ValueError, match="course cards were not found"):
        ImperialAdapter(minimum_expected_programmes=1).parse_catalog("<html></html>")
