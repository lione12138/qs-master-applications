from __future__ import annotations

from datetime import date

import pytest

from gradwindow.programme_adapters.auckland import (
    CATALOG_URL,
    DEADLINES_URL,
    LATE_YEAR_2026_URL,
    SEMESTER_ONE_2027_URL,
    AucklandAdapter,
)


def _row(
    name: str, faculty: str, slug: str, programme_type: str = "Masters degree"
) -> str:
    return f"""
    <li class="page-listing__item listing-item">
      <a class="listing-item__link" href="/en/study/study-options/find-a-study-option/{slug}.html">
        <p class="listing-item__heading" data-programme-name="{name}">{name}</p>
        <dl>
          <dd data-programme-faculty="{faculty}">{faculty}</dd>
          <dd data-programme-type="{programme_type}">{programme_type}</dd>
        </dl>
      </a>
    </li>
    """


CATALOG_HTML = "".join(
    (
        _row(
            "Master of Architecture",
            "Engineering and Design",
            "master-of-architecture-march",
        ),
        _row(
            "Master of Audiology",
            "Medical and Health Sciences",
            "master-of-audiology-maud",
        ),
        _row("Master of Data Science", "Science", "master-of-data-science-mdats"),
        _row(
            "Master of Information Technology",
            "Science",
            "master-of-information-technology-minfo-tech",
        ),
        _row(
            "Master of Physiotherapy Practice",
            "Science",
            "master-of-physiotherapy-practice-mphysioprac",
        ),
        _row(
            "Doctor of Philosophy",
            "The University of Auckland",
            "doctor-of-philosophy-phd",
            "Doctoral degree",
        ),
    )
)

SEMESTER_ONE_HTML = CATALOG_HTML
LATE_YEAR_HTML = _row(
    "Master of Architecture",
    "Engineering and Design",
    "master-of-architecture-march",
)

DEADLINES_HTML = """
<h2>Late Year 2026 application closing dates</h2>
<table><tbody>
  <tr><th>Programme of study</th><th>Application closing date</th></tr>
  <tr><td>All programmes not otherwise specified</td><td>11 November 2026</td></tr>
  <tr><td>Master of Information Technology</td><td>24 October 2026</td></tr>
</tbody></table>
<h2>Semester One 2027 application closing dates</h2>
<table><tbody>
  <tr><th>Programme of study</th><th>Application closing date</th></tr>
  <tr><td>Master of Audiology</td><td>1 July 2026</td></tr>
  <tr><td>Master of Health Sciences in Nutrition and Dietetics</td><td>1 July 2026</td></tr>
  <tr><td>International applications for postgraduate sub-doctoral programmes not otherwise specified</td><td>7 December 2026</td></tr>
</tbody></table>
"""

PHYSIOTHERAPY_URL = (
    "https://www.auckland.ac.nz/en/study/study-options/find-a-study-option/"
    "master-of-physiotherapy-practice-mphysioprac.html"
)
PHYSIOTHERAPY_HTML = """
<h1>Master of Physiotherapy Practice MPhysioPrac</h1>
<p>Next start date</p><p>2027 Semester One - 1 March</p>
<p>Applications open on 1 July and close on 1 October.</p>
"""


def _fetcher(url: str) -> str:
    pages = {
        CATALOG_URL: CATALOG_HTML,
        SEMESTER_ONE_2027_URL: SEMESTER_ONE_HTML,
        LATE_YEAR_2026_URL: LATE_YEAR_HTML,
        DEADLINES_URL: DEADLINES_HTML,
        PHYSIOTHERAPY_URL: PHYSIOTHERAPY_HTML,
    }
    return pages[url]


def _catalog():
    return AucklandAdapter(
        minimum_expected_programmes=5,
        maximum_expected_programmes=5,
        minimum_semester_one_programmes=5,
        maximum_semester_one_programmes=5,
        minimum_late_year_programmes=1,
        maximum_late_year_programmes=1,
        as_of=date(2026, 7, 17),
    ).parse_catalog_from_fetcher(_fetcher)


def test_auckland_adapter_discovers_the_official_masters_catalogue() -> None:
    catalog = _catalog()

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "auckland-architecture-master",
        "auckland-audiology-master",
        "auckland-data-science-master",
        "auckland-information-technology-master",
        "auckland-physiotherapy-practice-master",
    ]
    assert all(programme.degree_type == "Master" for programme in catalog.programmes)
    assert all("Doctor" not in programme.name for programme in catalog.programmes)


def test_auckland_adapter_maps_only_officially_scoped_future_deadlines() -> None:
    catalog = _catalog()
    programmes = {programme.id: programme for programme in catalog.programmes}

    architecture = programmes["auckland-architecture-master"]
    assert [(window.intake, window.closes_at) for window in architecture.windows] == [
        ("Late Year 2026", "2026-11-11"),
        ("Semester One 2027", "2026-12-07"),
    ]
    assert architecture.windows[1].applicant_categories == ["international-students"]

    information_technology = programmes["auckland-information-technology-master"]
    assert [
        (window.intake, window.closes_at) for window in information_technology.windows
    ] == [
        ("Late Year 2026", "2026-10-24"),
        ("Semester One 2027", "2026-12-07"),
    ]
    assert all(window.opens_at is None for window in information_technology.windows)


def test_auckland_adapter_does_not_coerce_yearless_policy_into_iso_dates() -> None:
    physiotherapy = next(
        item
        for item in _catalog().programmes
        if item.id == "auckland-physiotherapy-practice-master"
    )

    assert physiotherapy.windows == []
    assert physiotherapy.parse_status == "incomplete"
    assert "open on 1 July" in physiotherapy.deadline_text
    assert "year" in physiotherapy.deadline_text


def test_auckland_adapter_excludes_expired_named_exceptions_from_generic_rule() -> None:
    audiology = next(
        item for item in _catalog().programmes if item.id == "auckland-audiology-master"
    )

    assert audiology.windows == []
    assert "official named deadline has passed" in audiology.deadline_text


def test_auckland_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 5 master's programmes"):
        AucklandAdapter(
            minimum_expected_programmes=6,
            as_of=date(2026, 7, 17),
        ).parse_catalog_from_fetcher(_fetcher)


def test_auckland_adapter_rejects_non_official_catalogue_links() -> None:
    bad_catalogue = CATALOG_HTML.replace(
        "/en/study/study-options/find-a-study-option/master-of-architecture-march.html",
        "https://example.com/master-of-architecture-march.html",
    )

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return bad_catalogue
        return _fetcher(url)

    with pytest.raises(ValueError, match="non-official URL"):
        AucklandAdapter(
            minimum_expected_programmes=5,
            as_of=date(2026, 7, 17),
        ).parse_catalog_from_fetcher(fetcher)
