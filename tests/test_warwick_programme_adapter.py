import pytest

from gradwindow.programme_adapters.warwick import (
    APPLICATION_URL,
    CATALOG_URL,
    WarwickAdapter,
)

CATALOGUE = """
<div class="feed-item-list-item"><h2>Advanced Mechanical Engineering MSc</h2>
  <div class="feed-item-abstract"><div>Postgraduate Taught</div>
    <p><a href="https://warwick.ac.uk/study/postgraduate/courses/msc-advanced-mechanical-engineering">Advanced Mechanical Engineering (MSc)</a></p></div></div>
<div class="feed-item-list-item"><h2>Computer Science MSc</h2>
  <div class="feed-item-abstract"><div>Postgraduate Taught</div>
    <p><a href="https://warwick.ac.uk/study/postgraduate/courses/msc-computer-science">Computer Science (MSc)</a></p></div></div>
<div class="feed-item-list-item"><h2>Mathematics PhD</h2>
  <div class="feed-item-abstract"><div>Postgraduate Research</div>
    <p><a href="https://warwick.ac.uk/study/postgraduate/courses/phd-mathematics">Mathematics (PhD)</a></p></div></div>
"""


def test_warwick_adapter_discovers_taught_masters_and_reuses_cs_id() -> None:
    catalog = WarwickAdapter(minimum_expected_programmes=2).parse_catalog(CATALOGUE)

    assert [item.id for item in catalog.programmes] == [
        "warwick-advanced-mechanical-engineering-msc",
        "warwick-computer-science-msc",
    ]
    assert [item.degree_type for item in catalog.programmes] == ["MSc", "MSc"]
    assert all(item.windows == [] for item in catalog.programmes)


def test_warwick_adapter_rejects_a_truncated_catalogue() -> None:
    try:
        WarwickAdapter(minimum_expected_programmes=3).parse_catalog(CATALOGUE)
    except ValueError as error:
        assert "expected at least 3" in str(error)
    else:
        raise AssertionError("truncated Warwick catalogue was accepted")


def test_warwick_adapter_checks_the_official_application_policy() -> None:
    pages = {
        CATALOG_URL: CATALOGUE,
        APPLICATION_URL: (
            "Applications for most courses starting in September and October 2026 "
            "are now open. The on-time deadline is 2 August 2026."
        ),
    }

    catalog = WarwickAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
        lambda url: pages[url]
    )

    assert len(catalog.programmes) == 2
    with pytest.raises(ValueError, match="application policy"):
        WarwickAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
            lambda url: CATALOGUE if url == CATALOG_URL else "Unavailable"
        )
