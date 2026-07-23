from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from gradwindow.programme_adapters.toronto import (
    APPLICATION_URL,
    CATALOG_URL,
    TorontoAdapter,
    _deadline_windows,
)

COMPUTER_SCIENCE_URL = "https://www.sgs.utoronto.ca/programs/computer-science/"
INFORMATION_URL = "https://www.sgs.utoronto.ca/programs/information/"
AEROSPACE_URL = "https://www.sgs.utoronto.ca/programs/aerospace-and-engineering/"
PSYCHOLOGY_URL = "https://www.sgs.utoronto.ca/programs/psychology/"

CATALOG_HTML = f"""
<html><body><table>
  <thead><tr><th>Program</th><th>Graduate Unit</th><th>Degree Type</th></tr></thead>
  <tbody>
    <tr><td><a href="{COMPUTER_SCIENCE_URL}">Computer Science</a></td>
      <td>Computer Science</td><td>MSc / PhD</td></tr>
    <tr><td><a href="{INFORMATION_URL}">Information</a></td>
      <td>Information</td><td>MI / PhD</td></tr>
    <tr><td><a href="{AEROSPACE_URL}">Aerospace Science and Engineering</a></td>
      <td>Aerospace Studies</td><td>MASc / MEng / PhD</td></tr>
    <tr><td><a href="{PSYCHOLOGY_URL}">Psychology</a></td>
      <td>Psychology</td><td>PhD</td></tr>
  </tbody>
</table></body></html>
"""


def _detail(domestic: str, international: str) -> str:
    return f"""
    <html><body><h1>Programme</h1><table>
      <tr><th></th><th>Domestic</th><th>International</th></tr>
      <tr><th>Application deadline</th>
        <td>{domestic}</td><td>{international}</td></tr>
      <tr><th>Minimum admission average</th><td>B+</td><td>B+</td></tr>
    </table></body></html>
    """


DETAILS = {
    COMPUTER_SCIENCE_URL: _detail(
        "MSc, PhD: Fall 2027 entry 01-Dec-2026",
        "MSc, PhD: Fall 2027 entry 15-Nov-2026",
    ),
    INFORMATION_URL: _detail(
        "MI: Fall 2026 entry 31-Jan-2026 PhD: Fall 2026 entry 01-Dec-2025",
        "MI: Fall 2026 entry 31-Jan-2026 PhD: Fall 2026 entry 01-Dec-2025",
    ),
    AEROSPACE_URL: _detail(
        "MASc, PhD: Fall 2027 entry 15-Jan-2027 MEng: Fall 2027 entry 01-Jun-2027",
        "MASc, PhD: Fall 2027 entry 15-Jan-2027 MEng: Fall 2027 entry 01-Feb-2027",
    ),
}


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url in DETAILS:
        return DETAILS[url]
    raise AssertionError(url)


def test_toronto_adapter_expands_master_degrees_and_skips_doctoral_only_rows() -> None:
    catalog = TorontoAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "toronto-aerospace-and-engineering-masc",
        "toronto-aerospace-and-engineering-meng",
        "toronto-computer-science-msc",
        "toronto-information-mi",
    ]
    assert len(catalog.programmes) == 4


def test_toronto_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = TorontoAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.id == "toronto-computer-science-msc"
    )

    assert programme.name == "MSc in Computer Science"
    assert programme.degree_type == "MSc"
    assert programme.faculty == "Department of Computer Science"
    assert programme.application_url == APPLICATION_URL


def test_toronto_adapter_keeps_exact_closings_unresolved_without_an_opening() -> None:
    catalog = TorontoAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.id == "toronto-computer-science-msc"
    )

    assert [
        (
            window.applicant_categories,
            window.opens_at,
            window.closes_at,
            window.intake,
        )
        for window in programme.windows
    ] == [
        (["domestic"], None, "2026-12-01", "Fall 2027"),
        (["international"], None, "2026-11-15", "Fall 2027"),
    ]
    assert programme.parse_status == "incomplete"


def test_toronto_adapter_filters_stale_deadline_cycles() -> None:
    catalog = TorontoAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.id == "toronto-information-mi"
    )

    assert programme.windows == []
    assert programme.parse_status == "no-deadline"
    assert "Fall 2026" in programme.deadline_text


def test_toronto_adapter_keeps_a_valid_page_without_quick_facts() -> None:
    details = dict(DETAILS)
    details[INFORMATION_URL] = "<html><body><h1>Information</h1></body></html>"

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOG_HTML
        return details[url]

    catalog = TorontoAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(fetcher)
    programme = next(
        item for item in catalog.programmes if item.id == "toronto-information-mi"
    )

    assert programme.windows == []
    assert programme.parse_status == "no-deadline"
    assert "does not publish" in programme.deadline_text


def test_toronto_deadline_parser_preserves_multiple_named_rounds() -> None:
    table = BeautifulSoup(
        _detail(
            "MSc: Fall 2027 entry early deadline 15-Jan-2027 "
            "regular deadline 31-Mar-2027",
            "MSc: Fall 2027 entry 15-Jan-2027",
        ),
        "html.parser",
    ).table

    windows, _ = _deadline_windows(
        table,
        degree_type="MSc",
        source_url="https://www.sgs.utoronto.ca/programs/example/",
        intake_year=2027,
    )

    assert [(window.round, window.closes_at) for window in windows] == [
        ("Fall 2027 domestic early deadline", "2027-01-15"),
        ("Fall 2027 domestic regular deadline", "2027-03-31"),
        ("Fall 2027 international deadline", "2027-01-15"),
    ]


def test_toronto_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="expected at least 5"):
        TorontoAdapter(
            minimum_expected_programmes=5,
            workers=2,
        ).parse_catalog_from_fetcher(_fetcher)


def test_toronto_adapter_retries_a_transient_detail_failure() -> None:
    attempts = 0

    def fetcher(url: str) -> str:
        nonlocal attempts
        if url == COMPUTER_SCIENCE_URL:
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary disconnect")
        return _fetcher(url)

    catalog = TorontoAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(fetcher)

    assert len(catalog.programmes) == 4
    assert attempts == 2


def test_toronto_adapter_propagates_a_persistent_detail_failure() -> None:
    def fetcher(url: str) -> str:
        if url == COMPUTER_SCIENCE_URL:
            raise RuntimeError("still unavailable")
        return _fetcher(url)

    with pytest.raises(RuntimeError, match="still unavailable"):
        TorontoAdapter(
            minimum_expected_programmes=4,
            workers=2,
        ).parse_catalog_from_fetcher(fetcher)
