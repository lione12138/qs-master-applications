import pytest

from gradwindow.programme_adapters.auckland import (
    CATALOG_URL,
    DEADLINES_URL,
    AucklandAdapter,
)

CATALOGUE = """
<ul>
  <li class="page-listing__item listing-item"><a href="/en/study/study-options/find-a-study-option/master-of-data-science.html">
    <p data-programme-name="Master of Data Science">Master of Data Science</p>
    <dd data-programme-faculty="Science">Science</dd>
    <dd data-programme-type="Masters degree">Masters degree</dd></a></li>
  <li class="page-listing__item listing-item"><a href="/en/study/study-options/find-a-study-option/master-of-aerospace-engineering.html">
    <p data-programme-name="Master of Aerospace Engineering">Master of Aerospace Engineering</p>
    <dd data-programme-faculty="Engineering and Design">Engineering and Design</dd>
    <dd data-programme-type="Masters degree">Masters degree</dd></a></li>
  <li class="page-listing__item"><a href="/certificate"><p data-programme-name="Postgraduate Certificate">Certificate</p>
    <dd data-programme-type="Postgraduate diploma or certificate">Certificate</dd></a></li>
</ul>
"""


def test_auckland_adapter_discovers_only_masters_and_reuses_data_science_id() -> None:
    catalog = AucklandAdapter(minimum_expected_programmes=2).parse_catalog(CATALOGUE)

    assert [item.id for item in catalog.programmes] == [
        "auckland-master-of-aerospace-engineering",
        "auckland-data-science-master",
    ]
    assert catalog.programmes[0].faculty == "Engineering and Design"
    assert all(item.windows == [] for item in catalog.programmes)
    assert all("opening date" in item.deadline_text for item in catalog.programmes)


def test_auckland_adapter_rejects_a_truncated_catalogue() -> None:
    try:
        AucklandAdapter(minimum_expected_programmes=3).parse_catalog(CATALOGUE)
    except ValueError as error:
        assert "expected at least 3" in str(error)
    else:
        raise AssertionError("truncated Auckland catalogue was accepted")


def test_auckland_adapter_checks_the_official_deadline_policy() -> None:
    pages = {
        CATALOG_URL: CATALOGUE,
        DEADLINES_URL: "Semester One 2027 application closing dates",
    }

    catalog = AucklandAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
        lambda url: pages[url]
    )

    assert len(catalog.programmes) == 2
    with pytest.raises(ValueError, match="deadline policy"):
        AucklandAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
            lambda url: CATALOGUE if url == CATALOG_URL else "Unavailable"
        )
