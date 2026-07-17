from __future__ import annotations

import pytest

from gradwindow.programme_adapters.kyoto import (
    CATALOG_URL,
    INFORMATICS_ADMISSIONS_URL,
    KyotoAdapter,
)

PDF_URL = (
    "https://www.i.kyoto-u.ac.jp/assets/pdf/admission/application/master-2027-4-en.pdf"
)

CATALOG_HTML = """
<html><body><table>
  <tr><th>Graduate School website</th><th>Degree Programs</th><th>Courses</th><th>Staff</th></tr>
  <tr><td><a href="https://www.bun.kyoto-u.ac.jp/en/">Letters</a></td>
    <td>Master's Doctoral</td><td>Literature and History</td><td>Staff</td></tr>
  <tr><td><a href="https://www.i.kyoto-u.ac.jp/en/">Informatics</a></td>
    <td>Master's Doctoral</td><td>Informatics</td><td>Staff</td></tr>
  <tr><td><a href="https://law.kyoto-u.ac.jp/english/">Law</a></td>
    <td>Professional</td><td>Law School</td><td>Staff</td></tr>
  <tr><td><a href="https://www.sg.kyoto-u.ac.jp/sg/english/">Government</a></td>
    <td>Professional</td><td>Public Policy</td><td>Staff</td></tr>
</table></body></html>
"""

ADMISSIONS_HTML = f"""
<html><body><main><h1>Guidelines for Admission</h1>
  <h5>Guidelines for April 2027 Admission to the Master's Program</h5>
  <a href="{PDF_URL}">Download</a>
</main></body></html>
"""

PDF_TEXT = """
April 2027 Admission
Guidelines for Admission to the Master's Program
Intelligence Science and Technology
Social Informatics
Advanced Mathematical Sciences
Applied Mathematics and Physics
Systems Science
Communications and Computer Engineering
Data Science
Entrance Examination in August 2026
Submission of Application Materials by post
Date: Friday, June 5 - Friday, June 19, 2026
Application materials must arrive by 5:00 p.m.
"""

PAGES = {
    CATALOG_URL: CATALOG_HTML,
    INFORMATICS_ADMISSIONS_URL: ADMISSIONS_HTML,
    PDF_URL: PDF_TEXT,
}


def _adapter() -> KyotoAdapter:
    return KyotoAdapter(minimum_expected_programmes=9, maximum_expected_programmes=9)


def test_kyoto_adapter_combines_central_degrees_and_informatics_courses() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(PAGES.__getitem__)

    assert len(catalog.programmes) == 9
    assert len({item.id for item in catalog.programmes}) == 9
    assert catalog.application_opens_at == "2026-06-05"
    assert not any(item.name == "Law School" for item in catalog.programmes)
    assert any("Public Policy" in item.name for item in catalog.programmes)


def test_kyoto_adapter_preserves_existing_data_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(PAGES.__getitem__)
    programme = next(item for item in catalog.programmes if "Data Science" in item.name)

    assert programme.id == "kyoto-informatics-data-science-master"
    assert programme.department == "Graduate School of Informatics"


def test_kyoto_adapter_maps_pdf_window_only_to_informatics_courses() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(PAGES.__getitem__)
    informatics = [
        item
        for item in catalog.programmes
        if item.department == "Graduate School of Informatics"
    ]
    other = [item for item in catalog.programmes if item not in informatics]

    assert len(informatics) == 7
    assert all(len(item.windows) == 1 for item in informatics)
    assert all(item.windows[0].opens_at == "2026-06-05" for item in informatics)
    assert all(item.windows[0].closes_at == "2026-06-19" for item in informatics)
    assert all(item.windows == [] for item in other)


def test_kyoto_adapter_rejects_missing_exact_pdf_window() -> None:
    pages = {**PAGES, PDF_URL: PDF_TEXT.replace("June 19, 2026", "June 2026")}

    with pytest.raises(ValueError, match="exact postal application period"):
        _adapter().parse_catalog_from_fetcher(pages.__getitem__)


def test_kyoto_adapter_rejects_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 9 master's programmes"):
        KyotoAdapter(
            minimum_expected_programmes=10,
            maximum_expected_programmes=12,
        ).parse_catalog_from_fetcher(PAGES.__getitem__)
