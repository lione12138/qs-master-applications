from __future__ import annotations

import json

import pytest

from gradwindow.predictions import official_cycle_key
from gradwindow.programme_adapters.snu import (
    APPLICATION_URL,
    CATALOG_URL,
    GUIDE_URL,
    SNUAdapter,
)
from gradwindow.programme_windows import known_programme_window_candidates

APPLICATION_PAGE = f"""
<html><body>
  <h2>Admissions for Graduate, Spring 2027</h2>
  <a href="{GUIDE_URL}">PDF Download</a>
</body></html>
"""

GUIDE_TEXT = """
2027 Spring Graduate Admissions Guide for International Students
Timeline
Online Application Submission of Documents via Electronic Means
Monday, July 6, 2026, 10:00 - Thursday, July 9, 2026, 17:00
Programs Offered
"""

PDF_PAYLOAD = json.dumps(
    {
        "text": GUIDE_TEXT,
        "rows": [
            {
                "college": "College of Humanities",
                "department": "Philosophy",
                "major": "Eastern Philosophy Major",
                "m": "circle",
                "c": "",
                "d": "circle",
            },
            {
                "college": "College of Engineering",
                "department": "Computer Science and Engineering",
                "major": "Computer Science and Engineering",
                "m": "circle",
                "c": "circle",
                "d": "circle",
            },
            {
                "college": "College of Education",
                "department": "Education",
                "major": "Education",
                "m": "",
                "c": "",
                "d": "circle",
            },
            {
                "college": "Graduate School of Public Administration",
                "department": "Public Administration",
                "major": "Global Public Administration Major",
                "m": "circle",
                "c": "",
                "d": "",
            },
            {
                "college": "College of Fine Arts",
                "department": "Crafts and Design",
                "major": "Ceramics Major",
                "m": "circle",
                "c": "",
                "d": "",
            },
        ],
    }
)


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return APPLICATION_PAGE
    raise AssertionError(url)


def _adapter(*, target_intake_year: int = 2027) -> SNUAdapter:
    return SNUAdapter(
        minimum_expected_programmes=4,
        target_intake_year=target_intake_year,
        pdf_payload_fetcher=lambda url: PDF_PAYLOAD,
    )


def test_snu_adapter_discovers_only_master_eligible_programmes() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 4
    assert all("Education (" not in item.name for item in catalog.programmes)
    assert len({item.id for item in catalog.programmes}) == 4
    assert all(item.source_url == GUIDE_URL for item in catalog.programmes)
    assert all(item.application_url == APPLICATION_URL for item in catalog.programmes)


def test_snu_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "snu-computer-science-engineering-master"
    )

    assert programme.name == "Master's in Computer Science and Engineering"
    assert programme.faculty == "College of Engineering"
    assert programme.department == "Computer Science and Engineering"


def test_snu_adapter_uses_major_name_when_the_table_provides_one() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    philosophy = next(item for item in catalog.programmes if "Philosophy" in item.name)

    assert philosophy.name == "Master's in Eastern Philosophy"
    assert philosophy.department == "Philosophy"
    assert "eastern-philosophy" in philosophy.id


def test_snu_adapter_parses_the_exact_spring_2027_window() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = catalog.programmes[0]

    assert [
        (
            window.round,
            window.applicant_categories,
            window.opens_at,
            window.closes_at,
            window.intake,
            window.source_url,
        )
        for window in programme.windows
    ] == [
        (
            "International graduate admissions",
            ["international-students"],
            "2026-07-06",
            "2026-07-09",
            "Spring (March) 2027",
            GUIDE_URL,
        )
    ]
    assert programme.parse_status == "parsed"


def test_snu_known_programme_reuses_the_published_group_window() -> None:
    adapter = _adapter()
    catalog = adapter.parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "snu-computer-science-engineering-master"
    )
    existing = {
        "id": "snu-international-graduate-spring-2027",
        "universityId": "seoul-national-university",
        "scopeType": "programme-group",
        "scopeId": "snu-international-graduate-admissions",
        "intake": "Spring 2027",
        "intakeDetails": {
            "label": "Spring 2027",
            "cycleYear": 2027,
            "academicYearEnd": None,
            "term": "spring",
            "startMonth": 3,
        },
        "round": "International graduate admissions",
        "applicantCategories": ["international-students"],
        "opensAt": "2026-07-06",
        "closesAt": "2026-07-09",
        "applicationUrl": APPLICATION_URL,
        "sourceUrl": GUIDE_URL,
        "verifiedAt": "2026-06-14",
        "evidence": "Official guide.",
    }

    candidates = known_programme_window_candidates(
        adapter,
        programme,
        {
            "id": programme.id,
            "applicationUrl": APPLICATION_URL,
        },
        None,
        {official_cycle_key(existing): existing},
        {existing["id"]},
        "2026-07-17T00:00:00+00:00",
    )

    assert candidates == []


def test_snu_adapter_filters_a_stale_cycle() -> None:
    catalog = _adapter(target_intake_year=2028).parse_catalog_from_fetcher(_fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "Spring 2027" in programme.deadline_text for programme in catalog.programmes
    )


def test_snu_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 master's programmes"):
        SNUAdapter(
            minimum_expected_programmes=5,
            pdf_payload_fetcher=lambda url: PDF_PAYLOAD,
        ).parse_catalog_from_fetcher(_fetcher)
