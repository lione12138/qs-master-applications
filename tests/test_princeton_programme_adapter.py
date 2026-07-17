from __future__ import annotations

import pytest

from gradwindow.programme_adapters.princeton import (
    APPLICATION_URL,
    CATALOG_URL,
    DEADLINES_URL,
    PrincetonAdapter,
    reader_url,
)

CATALOG_MARKDOWN = """
| Departments & Programs | Program Offerings |
| --- | --- |
| [Architecture](http://gradschool.princeton.edu/academics/degrees-requirements/fields-study/architecture) | Ph.D. , M.Arch. |
| [Chemical and Biological Engineering](http://gradschool.princeton.edu/academics/degrees-requirements/fields-study/chemical-and-biological-engineering) | Ph.D. , M.S.E. , M.Eng. |
| [Electrical and Computer Engineering](http://gradschool.princeton.edu/academics/degrees-requirements/fields-study/electrical-and-computer-engineering) | Ph.D. , M.Eng. |
| [Anthropology](http://gradschool.princeton.edu/academics/degrees-requirements/fields-study/anthropology) | Ph.D. |
| [Digital Humanities](http://gradschool.princeton.edu/academics/degrees-requirements/fields-study/digital-humanities) | Certificate |
"""

DETAILS = {
    "architecture": """
        # Architecture
        ### Program Offerings:
        * Ph.D.
        * M.Arch.
        ## Apply
        Application deadline
        December 30, 11:59 p.m. Eastern Standard Time
        (This deadline is for applications for enrollment beginning in fall 2026)
        Program length
        Ph.D. 5 years, M.Arch. 2 or 3 years
    """,
    "chemical-and-biological-engineering": """
        # Chemical and Biological Engineering
        ### Program Offerings:
        * Ph.D.
        * M.S.E.
        * M.Eng.
        ## Apply
        Application deadline
        December 1, 11:59 p.m. Eastern Standard Time
        (This deadline is for applications for enrollment beginning in fall 2026)
        Program length
        Ph.D. 5 years, M.S.E. 2 years, M.Eng. 1 year
    """,
    "electrical-and-computer-engineering": """
        # Electrical and Computer Engineering
        ### Program Offerings:
        * Ph.D.
        * M.Eng.
        ## Apply
        Application deadline
        Ph.D. - December 15, 11:59 p.m. Eastern Standard Time;
        M.Eng. - December 30, 11:59 p.m.
        (This deadline is for applications for enrollment beginning in fall 2026)
        Program length
        Ph.D. 5 years, M.Eng. 1 year
    """,
}

DEADLINES_MARKDOWN = """
# Deadlines and Fees
The application for Fall 2026 admission is now closed.
The application for Fall 2027 will open in September 2026.
"""


def _official_url(slug: str) -> str:
    return f"{CATALOG_URL}/{slug}"


def _reader_fetcher(url: str) -> str:
    if not url.startswith("https://r.jina.ai/http://"):
        raise RuntimeError("HTTP 403")
    if url == reader_url(CATALOG_URL):
        return CATALOG_MARKDOWN
    if url == reader_url(DEADLINES_URL):
        return DEADLINES_MARKDOWN
    for slug, text in DETAILS.items():
        if url == reader_url(_official_url(slug)):
            return text
    raise AssertionError(url)


def test_princeton_adapter_discovers_terminal_masters_via_reader_fallback() -> None:
    catalog = PrincetonAdapter(
        minimum_expected_programmes=4
    ).parse_catalog_from_fetcher(_reader_fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "princeton-architecture-march",
        "princeton-chemical-and-biological-engineering-meng",
        "princeton-chemical-and-biological-engineering-mse",
        "princeton-electrical-and-computer-engineering-meng",
    ]
    assert [programme.windows[0].closes_at for programme in catalog.programmes] == [
        "2025-12-30",
        "2025-12-01",
        "2025-12-01",
        "2025-12-30",
    ]
    assert all(
        programme.windows[0].intake == "Fall 2026" for programme in catalog.programmes
    )
    assert all(
        programme.parse_status == "incomplete" for programme in catalog.programmes
    )
    assert all(
        programme.retrieval_method == "official-page-via-reader"
        for programme in catalog.programmes
    )


def test_princeton_adapter_preserves_official_urls_and_missing_opening_policy() -> None:
    catalog = PrincetonAdapter(
        minimum_expected_programmes=4
    ).parse_catalog_from_fetcher(_reader_fetcher)
    architecture = catalog.programmes[0]

    assert architecture.name == "M.Arch. in Architecture"
    assert architecture.degree_type == "MARCH"
    assert architecture.faculty == "Princeton University Graduate School"
    assert architecture.department == "Architecture"
    assert architecture.source_url == _official_url("architecture")
    assert architecture.application_url == APPLICATION_URL
    assert architecture.windows[0].source_url == _official_url("architecture")
    assert architecture.windows[0].opens_at is None
    assert "September 2026" in architecture.deadline_text
    assert "no exact opening date" in architecture.deadline_text


def test_princeton_adapter_uses_the_existing_computer_science_id() -> None:
    catalog_markdown = CATALOG_MARKDOWN.replace(
        "| [Anthropology]",
        "| [Computer Science](http://gradschool.princeton.edu/academics/degrees-requirements/fields-study/computer-science) | Ph.D. , M.S.E. |\n| [Anthropology]",
    )
    detail = """
        # Computer Science
        ## Apply
        Application deadline
        December 15, 11:59 p.m. Eastern Standard Time
        (This deadline is for applications for enrollment beginning in fall 2026)
        Program length
        Ph.D. 5 years, M.S.E. 2 years
    """

    def fetcher(url: str) -> str:
        if url == reader_url(CATALOG_URL):
            return catalog_markdown
        if url == reader_url(_official_url("computer-science")):
            return detail
        return _reader_fetcher(url)

    catalog = PrincetonAdapter(
        minimum_expected_programmes=5
    ).parse_catalog_from_fetcher(fetcher)
    computer_science = next(
        item for item in catalog.programmes if item.department == "Computer Science"
    )

    assert computer_science.id == "princeton-computer-science-mse"
    assert computer_science.name == "MSE in Computer Science"


def test_princeton_adapter_rejects_a_truncated_masters_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 master's programmes"):
        PrincetonAdapter(minimum_expected_programmes=5).parse_catalog_from_fetcher(
            _reader_fetcher
        )


def test_princeton_adapter_rejects_a_detail_without_a_current_cycle() -> None:
    def fetcher(url: str) -> str:
        if url == reader_url(_official_url("architecture")):
            return DETAILS["architecture"].replace("fall 2026", "fall 2025")
        return _reader_fetcher(url)

    with pytest.raises(ValueError, match="inconsistent application cycles"):
        PrincetonAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
            fetcher
        )


def test_princeton_adapter_requires_the_official_next_cycle_opening_policy() -> None:
    def fetcher(url: str) -> str:
        if url == reader_url(DEADLINES_URL):
            return "The application is currently closed."
        return _reader_fetcher(url)

    with pytest.raises(ValueError, match="next application cycle"):
        PrincetonAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
            fetcher
        )
