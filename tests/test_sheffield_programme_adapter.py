import pytest

from gradwindow.programme_adapters.sheffield import (
    CATALOG_URL,
    DEADLINES_URL,
    SheffieldAdapter,
)

CATALOGUE = """
<div class="courselisting"><span class="listcourse"><a href="/postgraduate/taught/courses/2026/advanced-computer-science-msc">Advanced Computer Science</a></span><span class="listaward">MSc</span></div>
<div class="courselisting"><span class="listcourse"><a href="/postgraduate/taught/courses/2026/applied-linguistics-and-tesol-ma">Applied Linguistics and TESOL</a></span><span class="listaward">MA</span></div>
<div class="courselisting"><span class="listcourse"><a href="/postgraduate/taught/courses/2026/sheffield-edd">The Sheffield EdD</a></span><span class="listaward">EdD</span></div>
"""


def test_sheffield_adapter_discovers_masters_and_reuses_existing_ids() -> None:
    catalog = SheffieldAdapter(minimum_expected_programmes=2).parse_catalog(CATALOGUE)

    assert [item.id for item in catalog.programmes] == [
        "sheffield-advanced-computer-science-msc",
        "sheffield-applied-linguistics-and-tesol-ma",
    ]
    assert [item.degree_type for item in catalog.programmes] == ["MSc", "MA"]
    assert all(item.windows == [] for item in catalog.programmes)
    assert all("exceptions" in item.deadline_text for item in catalog.programmes)


def test_sheffield_adapter_rejects_a_truncated_catalogue() -> None:
    try:
        SheffieldAdapter(minimum_expected_programmes=3).parse_catalog(CATALOGUE)
    except ValueError as error:
        assert "expected at least 3" in str(error)
    else:
        raise AssertionError("truncated Sheffield catalogue was accepted")


def test_sheffield_adapter_checks_the_official_deadline_exceptions() -> None:
    pages = {
        CATALOG_URL: CATALOGUE,
        DEADLINES_URL: "A few courses starting in September use different dates.",
    }

    catalog = SheffieldAdapter(
        minimum_expected_programmes=2
    ).parse_catalog_from_fetcher(lambda url: pages[url])

    assert len(catalog.programmes) == 2
    with pytest.raises(ValueError, match="deadline exceptions"):
        SheffieldAdapter(minimum_expected_programmes=2).parse_catalog_from_fetcher(
            lambda url: CATALOGUE if url == CATALOG_URL else "Unavailable"
        )
