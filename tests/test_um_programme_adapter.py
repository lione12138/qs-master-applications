from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.um import (
    HOW_TO_APPLY_URL,
    PROGRAMMES_URL,
    UMAdapter,
)

BROCHURE_URL = "https://study.um.edu.my/doc/brochures/brochure-postgraduate-2026.pdf"

PROGRAMMES_HTML = f"""
<main>
  <section><h2>Undergraduate</h2><a href="undergraduate.pdf">View Brochure</a></section>
  <section><h2>Postgraduate</h2><a href="{BROCHURE_URL}">View Brochure</a></section>
</main>
"""

HOW_TO_APPLY_HTML = """
<table><tr><td>Unrelated undergraduate table</td></tr></table>
<table>
  <tr>
    <td>CHANNELS</td><td>INTAKE</td><td>OPEN APPLICATION</td>
    <td>APPLICATION DEADLINE</td><td>PROGRAMMES SEARCH</td>
  </tr>
  <tr>
    <td>POSTGRADUATE - FOR MALAYSIAN AND INTERNATIONAL</td>
    <td>Semester I (October) Intake, Academic Session 2026/2027</td>
    <td>09 Feb 2026</td><td>30 Aug 2026</td>
    <td>Level of Study: Master Mode of Programme: Coursework Mixed Mode</td>
  </tr>
  <tr>
    <td>POSTGRADUATE - FOR MALAYSIAN AND INTERNATIONAL</td>
    <td>Term I (June) Intake, Academic Session 2026/2027</td>
    <td>22 Dec 2025</td><td>30 Apr 2026</td>
    <td>Level of Study: Master Mode of Programme: Clinical</td>
  </tr>
  <tr>
    <td>POSTGRADUATE - FOR MALAYSIAN</td>
    <td rowspan="2">Semester I (October) Intake, Academic Session 2026/2027</td>
    <td>12 Feb 2026</td><td>31 July 2026</td>
    <td>Postgraduate Diploma in Education Mode of Programme: Coursework</td>
  </tr>
  <tr>
    <td>POSTGRADUATE - FOR MALAYSIAN AND INTERNATIONAL</td>
    <td>27 April 2026</td><td>22 Nov 2026</td>
    <td>Level of Study: Master Mode of Programme: Research</td>
  </tr>
</table>
"""

PAYLOAD = json.dumps(
    {
        "entries": [
            {
                "faculty": "FACULTY OF COMPUTER SCIENCE AND INFORMATION TECHNOLOGY",
                "name": "Master of Computer Science (Applied Computing)",
                "mode": "CW",
            },
            {
                "faculty": "FACULTY OF BUSINESS AND ECONOMICS",
                "name": "Master of Business Administration",
                "mode": "MM",
            },
            {
                "faculty": "FACULTY OF ARTS AND SOCIAL SCIENCES",
                "name": "Master of Arts",
                "mode": "RS",
            },
            {
                "faculty": "FACULTY OF CREATIVE ARTS",
                "name": "Master of Arts",
                "mode": "RS/MM",
            },
            {
                "faculty": "FACULTY OF MEDICINE",
                "name": "Master of Surgery",
                "mode": "CL",
            },
        ]
    }
)


def _fetcher(url: str) -> str:
    if url == PROGRAMMES_URL:
        return PROGRAMMES_HTML
    if url == HOW_TO_APPLY_URL:
        return HOW_TO_APPLY_HTML
    raise AssertionError(url)


def _adapter(**kwargs) -> UMAdapter:
    kwargs.setdefault("minimum_expected_programmes", 5)
    kwargs.setdefault("maximum_expected_programmes", 6)
    kwargs.setdefault("pdf_payload_fetcher", lambda url: PAYLOAD)
    return UMAdapter(**kwargs)


def test_um_adapter_discovers_master_programmes_and_preserves_duplicate_names() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 5
    arts = [item for item in catalog.programmes if item.name == "Master of Arts"]
    assert len(arts) == 2
    assert len({item.id for item in arts}) == 2
    assert {item.faculty for item in arts} == {
        "Faculty of Arts and Social Sciences",
        "Faculty of Creative Arts",
    }


def test_um_adapter_preserves_existing_applied_computing_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    applied_computing = next(
        item for item in catalog.programmes if "Applied Computing" in item.name
    )

    assert applied_computing.id == "um-computer-science-applied-computing-master"
    assert applied_computing.source_url == BROCHURE_URL


def test_um_adapter_maps_official_windows_by_programme_mode() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at == "2025-12-22"
    by_name = {item.name: item for item in catalog.programmes}
    coursework = by_name["Master of Computer Science (Applied Computing)"]
    assert [(w.opens_at, w.closes_at, w.intake) for w in coursework.windows] == [
        ("2026-02-09", "2026-08-30", "October 2026")
    ]
    clinical = by_name["Master of Surgery"]
    assert [(w.opens_at, w.closes_at, w.intake) for w in clinical.windows] == [
        ("2025-12-22", "2026-04-30", "June 2026")
    ]
    creative_arts = next(
        item
        for item in catalog.programmes
        if item.name == "Master of Arts" and item.faculty == "Faculty of Creative Arts"
    )
    assert {(w.round, w.opens_at, w.closes_at) for w in creative_arts.windows} == {
        ("Coursework and mixed-mode admission", "2026-02-09", "2026-08-30"),
        ("Research admission", "2026-04-27", "2026-11-22"),
    }
    assert all(
        window.applicant_categories == ["all"] and window.source_url == HOW_TO_APPLY_URL
        for item in catalog.programmes
        for window in item.windows
    )


def test_um_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 5 master's programmes"):
        _adapter(minimum_expected_programmes=6).parse_catalog_from_fetcher(_fetcher)


def test_um_adapter_rejects_a_missing_official_window() -> None:
    def fetcher(url: str) -> str:
        html = _fetcher(url)
        if url == HOW_TO_APPLY_URL:
            return html.replace("27 April 2026", "To be announced")
        return html

    with pytest.raises(ValueError, match="exact Research application window"):
        _adapter().parse_catalog_from_fetcher(fetcher)
