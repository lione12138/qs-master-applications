from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.yonsei import (
    APPLICATION_URL,
    GUIDE_INDEX_URL,
    MIRAE_GUIDE_URL,
    SCHEDULE_URL,
    SEOUL_GUIDE_URL,
    YonseiAdapter,
)

GUIDE_INDEX_HTML = f"""
<html><body>
  <a href="{SEOUL_GUIDE_URL}">(Seoul Campus) Spring 2026 Guideline (English, PDF)</a>
  <a href="{MIRAE_GUIDE_URL}">(Mirae Campus) Spring 2026 Guideline (English, PDF)</a>
</body></html>
"""

SCHEDULE_HTML = """
<html><body><table>
  <tr><th>입학시기</th><th>전형별</th><th>원서접수</th></tr>
  <tr><td>2027년 전기</td><td>일반전형 (2027년 3월 신입학)</td>
      <td>2026. 10. 7.(수) 10:00 ~ 10. 14.(수) 17:00 마감</td></tr>
  <tr><td></td><td>외국인전형 (2027년 3월 신입학)</td>
      <td>2026. 10. 7.(수) 10:00 ~ 10. 14.(수) 17:00 마감</td></tr>
</table></body></html>
"""

SEOUL_PAYLOAD = json.dumps(
    {
        "guideYear": 2026,
        "rows": [
            {
                "campus": "Sinchon Campus",
                "college": "College of Computing",
                "department": "Computer Science",
                "master": True,
            },
            {
                "campus": "Sinchon Campus",
                "college": "College of Engineering",
                "department": "Mechanical Engineering",
                "master": True,
            },
            {
                "campus": "Sinchon Campus",
                "college": "College of Engineering",
                "department": "Science and Technology Policy",
                "master": False,
            },
        ],
    }
)

MIRAE_PAYLOAD = json.dumps(
    {
        "guideYear": 2026,
        "rows": [
            {
                "campus": "Mirae Campus",
                "college": "Software and Digital Healthcare Convergence",
                "department": "Computer Science",
                "master": True,
            },
            {
                "campus": "Mirae Campus",
                "college": "Nursing (Wonju)",
                "department": "Nursing",
                "master": True,
            },
        ],
    }
)


def _fetcher(url: str) -> str:
    pages = {
        GUIDE_INDEX_URL: GUIDE_INDEX_HTML,
        SCHEDULE_URL: SCHEDULE_HTML,
    }
    return pages[url]


def _pdf_fetcher(url: str) -> str:
    return {SEOUL_GUIDE_URL: SEOUL_PAYLOAD, MIRAE_GUIDE_URL: MIRAE_PAYLOAD}[url]


def _adapter(*, target_intake_year: int = 2027) -> YonseiAdapter:
    return YonseiAdapter(
        minimum_expected_programmes=4,
        target_intake_year=target_intake_year,
        pdf_payload_fetcher=_pdf_fetcher,
    )


def test_yonsei_adapter_discovers_only_master_eligible_programmes() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 4
    assert len({item.id for item in catalog.programmes}) == 4
    assert not any("Technology Policy" in item.name for item in catalog.programmes)
    assert {item.faculty for item in catalog.programmes} >= {
        "Sinchon Campus | College of Computing",
        "Mirae Campus | Nursing (Wonju)",
    }


def test_yonsei_adapter_preserves_existing_seoul_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "yonsei-computer-science-master"
    )

    assert programme.name == "Master's in Computer Science"
    assert programme.application_url == APPLICATION_URL
    assert programme.source_url == SEOUL_GUIDE_URL


def test_yonsei_adapter_keeps_same_named_mirae_programme_distinct() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    computer_science = [
        item
        for item in catalog.programmes
        if item.name == "Master's in Computer Science"
    ]

    assert len(computer_science) == 2
    assert {item.id for item in computer_science} == {
        "yonsei-computer-science-master",
        "yonsei-mirae-campus-computer-science-master",
    }


def test_yonsei_adapter_parses_exact_spring_2027_international_window() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert all(
        [
            (
                window.round,
                window.applicant_categories,
                window.opens_at,
                window.closes_at,
                window.intake,
                window.source_url,
            )
            for window in programme.windows
        ]
        == [
            (
                "International student track",
                ["international-students"],
                "2026-10-07",
                "2026-10-14",
                "Spring (March) 2027",
                SCHEDULE_URL,
            )
        ]
        for programme in catalog.programmes
    )


def test_yonsei_adapter_filters_stale_target_cycle() -> None:
    catalog = _adapter(target_intake_year=2028).parse_catalog_from_fetcher(_fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )


def test_yonsei_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 master's programmes"):
        YonseiAdapter(
            minimum_expected_programmes=5,
            pdf_payload_fetcher=_pdf_fetcher,
        ).parse_catalog_from_fetcher(_fetcher)
