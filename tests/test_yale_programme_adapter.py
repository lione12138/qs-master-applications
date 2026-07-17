from __future__ import annotations

import pytest

from gradwindow.programme_adapters.yale import (
    APPLICATION_PROCESS_URL,
    CATALOG_URL,
    DATES_URL,
    TERMINAL_DEGREES_URL,
    YaleAdapter,
)

CATALOG_HTML = """
<main>
  <ul class="program-listing">
    <li class="program-listing__item">
      <div class="program-listing__item--info">
        <a class="h5 arrow-link" href="/programs-of-study/african-studies">
          African Studies
        </a>
        <ul>
          <li class="deadline"><span class="date">January 2</span></li>
          <li><em>Social Sciences</em></li>
        </ul>
      </div>
      <div class="program-listing__degree"><ul>
        <li>MA - Master of Arts</li>
      </ul></div>
    </li>
    <li class="program-listing__item">
      <div class="program-listing__item--info">
        <a class="h5 arrow-link" href="/programs-of-study/computer-science">
          Computer Science
        </a>
        <ul>
          <li class="deadline">
            <span class="date">PhD - December 15</span>
            <span class="date">MS - January 2</span>
          </li>
          <li><em>Physical Sciences &amp; Engineering</em></li>
        </ul>
      </div>
      <div class="program-listing__degree"><ul>
        <li>PhD - Doctor of Philosophy</li>
        <li>MS - Master of Science</li>
      </ul></div>
    </li>
    <li class="program-listing__item">
      <div class="program-listing__item--info">
        <a class="h5 arrow-link" href="/programs-of-study/statistics-data-science">
          Statistics &amp; Data Science
        </a>
        <ul>
          <li class="deadline">
            <span class="date">MS - December 1</span>
            <span class="date">PhD - December 1*</span>
          </li>
          <li><em>Social Sciences</em></li>
        </ul>
      </div>
      <div class="program-listing__degree"><ul>
        <li>PhD - Doctor of Philosophy</li>
        <li>MS - Master of Science</li>
      </ul></div>
    </li>
    <li class="program-listing__item">
      <div class="program-listing__item--info">
        <a class="h5 arrow-link" href="/programs-of-study/economics">
          Economics
        </a>
        <ul>
          <li class="deadline"><span class="date">December 1</span></li>
          <li><em>Social Sciences</em></li>
        </ul>
      </div>
      <div class="program-listing__degree"><ul>
        <li>PhD - Doctor of Philosophy</li>
        <li>MA - Master of Arts</li>
      </ul></div>
    </li>
  </ul>
</main>
"""

DATES_HTML = """
<main><div class="wysiwyg">
  <h2>December 1, 2026</h2>
  <p>Application deadline for:</p>
  <ul>
    <li><strong>Statistics and Data Science*</strong></li>
  </ul>
  <h2>December 15, 2026</h2>
  <p>Application deadline for:</p>
  <ul>
    <li><strong>Computer Science (PhD)</strong></li>
  </ul>
  <h2>January 2, 2027</h2>
  <p>Application deadline for:</p>
  <ul>
    <li><strong>African Studies</strong></li>
    <li><strong>Computer Science (MS)</strong></li>
  </ul>
  <p>All application deadlines are as of 11:59 pm Eastern time.</p>
</div></main>
"""

PROCESS_HTML = """
<main>
  <p>The application for Fall 2026 entry is now closed.</p>
  <p>
    The application for Fall 2027 entry will be available in mid-September 2026.
  </p>
</main>
"""

TERMINAL_DEGREES_HTML = """
<main>
  <h2>Terminal M.A./M.S. Degrees</h2>
  <p>
    The M.A. and M.S. degrees are offered as terminal degrees in the following
    departments and programs: African Studies, Computer Science, and Statistics
    and Data Science. The residence and tuition requirements follow.
  </p>
</main>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url == DATES_URL:
        return DATES_HTML
    if url == APPLICATION_PROCESS_URL:
        return PROCESS_HTML
    if url == TERMINAL_DEGREES_URL:
        return TERMINAL_DEGREES_HTML
    raise AssertionError(url)


def test_yale_adapter_keeps_only_terminal_masters_and_exact_closing_dates() -> None:
    catalog = YaleAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "yale-african-studies-ma",
        "yale-computer-science-ms",
        "yale-statistics-data-science-ms",
    ]
    assert all(
        programme.parse_status == "incomplete" for programme in catalog.programmes
    )
    assert [programme.windows[0].closes_at for programme in catalog.programmes] == [
        "2027-01-02",
        "2027-01-02",
        "2026-12-01",
    ]
    assert all(
        programme.windows[0].opens_at is None for programme in catalog.programmes
    )
    assert all(
        programme.windows[0].intake == "Fall 2027" for programme in catalog.programmes
    )


def test_yale_adapter_uses_masters_deadline_and_preserves_existing_cs_record() -> None:
    catalog = YaleAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )
    computer_science = next(
        programme
        for programme in catalog.programmes
        if programme.id == "yale-computer-science-ms"
    )

    assert computer_science.name == "MS in Computer Science"
    assert computer_science.degree_type == "MS"
    assert computer_science.faculty == "Graduate School of Arts and Sciences"
    assert computer_science.department == "Computer Science"
    assert computer_science.source_url == (
        "https://gsas.yale.edu/programs-of-study/computer-science"
    )
    assert computer_science.application_url == APPLICATION_PROCESS_URL
    assert computer_science.windows[0].source_url == DATES_URL
    assert "mid-September 2026" in computer_science.deadline_text
    assert "exact opening date" in computer_science.deadline_text


def test_yale_adapter_rejects_a_truncated_terminal_masters_catalogue() -> None:
    with pytest.raises(
        ValueError, match="only contained 3 terminal master's programmes"
    ):
        YaleAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(_fetcher)


def test_yale_adapter_rejects_a_deadline_page_without_the_current_intake() -> None:
    def fetcher(url: str) -> str:
        if url == DATES_URL:
            return DATES_HTML.replace("2027", "2026")
        return _fetcher(url)

    with pytest.raises(ValueError, match="Fall 2027"):
        YaleAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(fetcher)
