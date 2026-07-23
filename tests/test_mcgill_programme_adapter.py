from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from gradwindow.programme_adapters.mcgill import (
    APPLICATION_URL,
    CYCLE_URL,
    SITEMAP_URL,
    McGillAdapter,
    _academic_unit,
    _cycle_date,
    _fall_windows,
)

CS_THESIS_URL = "https://www.mcgill.ca/gradapplicants/program/computer-science-msc"
CS_NON_THESIS_URL = (
    "https://www.mcgill.ca/gradapplicants/program/computer-science-msc-non-thesis"
)
MPP_URL = "https://www.mcgill.ca/gradapplicants/program/public-policy-mpp"
NURSE_URL = (
    "https://www.mcgill.ca/gradapplicants/program/nurse-practitioner-msc-non-thesis"
)

SITEMAP_XML = f"""
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{CS_THESIS_URL}</loc></url>
  <url><loc>{CS_NON_THESIS_URL}</loc></url>
  <url><loc>{MPP_URL}</loc></url>
  <url><loc>{NURSE_URL}</loc></url>
  <url><loc>https://www.mcgill.ca/gradapplicants/program/computer-science-phd</loc></url>
  <url><loc>https://www.mcgill.ca/gradapplicants/program/cybersecurity-grad-cert</loc></url>
</urlset>
"""

CYCLE_HTML = """
<main>
  <h1>Application period for admission in September 2027 to Graduate Studies</h1>
  <p>Tuesday, September 15, 2026 to Tuesday, June 15, 2027</p>
  <p>Each McGill graduate department sets its own application deadlines.</p>
</main>
"""


def _programme_html(
    title: str,
    description: str,
    rows: list[tuple[str, str, str, str]] | None,
) -> str:
    table = ""
    if rows is not None:
        body = "".join(
            "<tr>"
            f"<td>{intake}</td><td>{opens}</td><td>{international}</td>"
            f"<td>{domestic}</td>"
            "</tr>"
            for intake, opens, international, domestic in rows
        )
        table = f"""
        <table>
          <thead><tr>
            <th>Intake</th><th>Applications Open</th>
            <th>Application Deadlines - International</th>
            <th>Application Deadlines - Domestic (Canadian, Permanent Resident of Canada)</th>
          </tr></thead>
          <tbody>{body}</tbody>
        </table>
        """
    return f"""
    <main>
      <h1>{title}</h1>
      <h2>Program Description</h2>
      <p>{description}</p>
      <h2>Application Deadlines</h2>
      {table}
    </main>
    """


DETAILS = {
    CS_THESIS_URL: _programme_html(
        "Computer Science (M.Sc.)",
        "The Master of Science in Computer Science (Thesis) offered by the "
        "School of Computer Science in the Faculty of Science is research-intensive.",
        [
            ("FALL", "September 15", "December 15", "February 15"),
            ("WINTER", "N/A", "N/A", "N/A"),
        ],
    ),
    CS_NON_THESIS_URL: _programme_html(
        "Computer Science (M.Sc.)",
        "The Master of Science in Computer Science (Non-Thesis) offered by the "
        "School of Computer Science in the Faculty of Science is course-based.",
        [("FALL", "September 15", "January 15", "May 1")],
    ),
    MPP_URL: _programme_html(
        "Public Policy (M.P.P.)",
        "The Master of Public Policy offered by the Max Bell School of Public "
        "Policy in McGill University is a professional program.",
        [
            ("FALL", "N/A", "N/A", "N/A"),
            ("SUMMER", "September 1", "January 15", "March 15"),
        ],
    ),
    NURSE_URL: _programme_html(
        "Nurse Practitioner (M.Sc.A.)",
        "The Master of Science Applied offered by the Ingram School of Nursing "
        "in the Faculty of Medicine and Health Sciences is professional.",
        None,
    ),
}


def _fetcher(url: str) -> str:
    if url == SITEMAP_URL:
        return SITEMAP_XML
    if url == CYCLE_URL:
        return CYCLE_HTML
    if url in DETAILS:
        return DETAILS[url]
    raise AssertionError(url)


def test_mcgill_adapter_discovers_masters_and_skips_non_master_pages() -> None:
    catalog = McGillAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at == "2026-09-15"
    assert [programme.id for programme in catalog.programmes] == [
        "mcgill-computer-science-msc-non-thesis",
        "mcgill-computer-science-msc-thesis",
        "mcgill-nurse-practitioner-msc-non-thesis",
        "mcgill-public-policy-mpp",
    ]
    assert len(catalog.programmes) == 4


def test_mcgill_adapter_creates_exact_fall_windows_by_applicant_category() -> None:
    catalog = McGillAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    thesis = next(item for item in catalog.programmes if item.id.endswith("msc-thesis"))

    assert [
        (window.applicant_categories, window.opens_at, window.closes_at)
        for window in thesis.windows
    ] == [
        (["international-students"], "2026-09-15", "2026-12-15"),
        (["domestic-students"], "2026-09-15", "2027-02-15"),
    ]
    assert all(window.intake == "Fall 2027" for window in thesis.windows)
    assert all(window.source_url == CS_THESIS_URL for window in thesis.windows)
    assert thesis.parse_status == "parsed"


def test_mcgill_adapter_preserves_tracks_faculty_and_existing_computing_id() -> None:
    catalog = McGillAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    thesis = next(item for item in catalog.programmes if item.id.endswith("msc-thesis"))
    non_thesis = next(
        item for item in catalog.programmes if item.id.endswith("msc-non-thesis")
    )

    assert thesis.id == "mcgill-computer-science-msc-thesis"
    assert thesis.name == "MSc in Computer Science (Thesis)"
    assert non_thesis.name == "Computer Science (M.Sc.) (Non-Thesis)"
    assert thesis.degree_type == "M.Sc."
    assert thesis.faculty == "Faculty of Science"
    assert thesis.department == "School of Computer Science"
    assert thesis.application_url == APPLICATION_URL


def test_mcgill_adapter_rejects_an_overlong_academic_unit_match() -> None:
    description = (
        "This program is offered by the cultural, social, and historical research "
        "on Asia from literature to migration and visual art in the Faculty of Arts "
        "offers interdisciplinary training and specialization is distinctive."
    )

    assert _academic_unit(description) == ("", "McGill University")


def test_mcgill_adapter_keeps_programmes_without_a_safe_fall_window() -> None:
    catalog = McGillAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    monitored = [item for item in catalog.programmes if not item.windows]

    assert [item.id for item in monitored] == [
        "mcgill-nurse-practitioner-msc-non-thesis",
        "mcgill-public-policy-mpp",
    ]
    assert all(item.parse_status == "no-deadline" for item in monitored)
    assert "Fall 2027" in monitored[0].deadline_text


def test_mcgill_adapter_preserves_explicit_years_for_special_cohorts() -> None:
    assert _cycle_date("November 15, 2025", 2027) == "2025-11-15"
    assert _cycle_date("September 15, 2026", 2027) == "2026-09-15"
    assert _cycle_date("July 1", 2027, not_before="2026-09-15") == "2027-07-01"


def test_mcgill_adapter_parses_french_fall_deadline_tables() -> None:
    table = BeautifulSoup(
        """
        <table>
          <tr><th>Période</th><th>Applications Ouvertes</th>
            <th>Dates Limites Des Demandes - International</th>
            <th>Dates Limites Des Demandes - Canadien</th></tr>
          <tr><td>AUTOMNE (FALL)</td><td>15 septembre</td>
            <td>15 janvier</td><td>15 mai</td></tr>
        </table>
        """,
        "html.parser",
    ).table

    windows, _ = _fall_windows(
        table,
        source_url="https://www.mcgill.ca/gradapplicants/program/french-ma",
        intake_year=2027,
        cycle_opens_at="2026-09-15",
    )

    assert [(window.opens_at, window.closes_at) for window in windows] == [
        ("2026-09-15", "2027-01-15"),
        ("2026-09-15", "2027-05-15"),
    ]


def test_mcgill_adapter_rejects_a_truncated_masters_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 master's programmes"):
        McGillAdapter(
            minimum_expected_programmes=5,
            workers=2,
        ).parse_catalog_from_fetcher(_fetcher)


def test_mcgill_adapter_retries_a_transient_detail_failure() -> None:
    attempts = 0

    def fetcher(url: str) -> str:
        nonlocal attempts
        if url == CS_THESIS_URL:
            attempts += 1
            if attempts == 1:
                raise RuntimeError("server disconnected")
        return _fetcher(url)

    catalog = McGillAdapter(
        minimum_expected_programmes=4,
        workers=2,
    ).parse_catalog_from_fetcher(fetcher)

    assert len(catalog.programmes) == 4
    assert attempts == 2


def test_mcgill_adapter_requires_the_official_fall_cycle() -> None:
    def fetcher(url: str) -> str:
        if url == CYCLE_URL:
            return CYCLE_HTML.replace("September 2027", "September 2026")
        return _fetcher(url)

    with pytest.raises(ValueError, match="Fall 2027 application period"):
        McGillAdapter(
            minimum_expected_programmes=4,
            workers=2,
        ).parse_catalog_from_fetcher(fetcher)
