from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.zju import (
    CATALOG_URL,
    EXISTING_CS_ID,
    ZJUAdapter,
)

CHINESE_URL = "https://iczu.zju.edu.cn/_upload/current/chinese-2026.pdf"
ENGLISH_URL = "https://iczu.zju.edu.cn/_upload/current/english-2026.pdf"

CATALOG_HTML = f"""
<main>
  <a href="{CHINESE_URL}">Catalog of Chinese-taught Master's Degree programs 2026</a>
  <a href="{ENGLISH_URL}">Catalog of English-taught Master's Degree programs 2026</a>
</main>
"""


def _payload(language: str, rows: list[list[str | None]]) -> str:
    return json.dumps(
        {
            "pages": [
                {
                    "rows": [
                        [
                            f"{language}-taught Master's Degree Programs 2026",
                            None,
                            None,
                            None,
                            None,
                        ],
                        [
                            "Schools/Colleges/Departments",
                            "Disciplines/Programs",
                            "Duration of Studies",
                            "Tuition",
                            "Other Requirements and Tips",
                        ],
                        *rows,
                    ]
                }
            ]
        }
    )


PAYLOADS = {
    CHINESE_URL: _payload(
        "Chinese",
        [
            [
                "College of Computer Science and Technology\nhttp://www.cs.zju.edu.cn/",
                "Computer Science and Technology",
                "3 years",
                "RMB 32,800",
                "",
            ],
            [None, "Software Engineering", "3 years", "RMB 32,800", ""],
        ],
    ),
    ENGLISH_URL: _payload(
        "English",
        [
            [
                "College of Computer Science and Technology\nhttp://www.en.cs.zju.edu.cn/",
                "Computer Science and Technology",
                "3 years",
                "RMB 36,800",
                "",
            ],
            [
                "http://previous.zju.edu.cn/ International Business School, "
                "Zhejiang University https://zibs.zju.edu.cn/enzibs/",
                "Finance (iMF) (Professional)",
                "2 years",
                "RMB 180,000",
                "Application Deadline: May 31st, 2026",
            ],
        ],
    ),
}


def _fetcher(url: str) -> str:
    assert url == CATALOG_URL
    return CATALOG_HTML


def _adapter(**kwargs) -> ZJUAdapter:
    return ZJUAdapter(
        minimum_expected_chinese_programmes=2,
        minimum_expected_english_programmes=2,
        pdf_payload_fetcher=lambda url: PAYLOADS[url],
        **kwargs,
    )


def test_zju_adapter_discovers_both_teaching_languages() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 4
    assert {item.name.rsplit(" (", 1)[-1] for item in catalog.programmes} == {
        "Chinese-taught)",
        "English-taught)",
    }
    assert {item.faculty for item in catalog.programmes} == {
        "College of Computer Science and Technology",
        "International Business School, Zhejiang University",
    }


def test_zju_adapter_preserves_existing_english_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    english_cs = next(
        item
        for item in catalog.programmes
        if item.name == "Computer Science and Technology (English-taught)"
    )

    assert english_cs.id == EXISTING_CS_ID
    assert len({item.id for item in catalog.programmes}) == 4


def test_zju_adapter_keeps_completed_cycle_deadlines_out_of_windows() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert all(item.windows == [] for item in catalog.programmes)
    assert all(item.parse_status == "no-deadline" for item in catalog.programmes)
    assert all(
        "No date is carried forward" in item.deadline_text
        for item in catalog.programmes
    )


def test_zju_adapter_rejects_stale_catalogues() -> None:
    with pytest.raises(ValueError, match="expected 2027 or later"):
        _adapter(minimum_catalog_year=2027).parse_catalog_from_fetcher(_fetcher)


def test_zju_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="Chinese-taught catalogue only contained 2"):
        ZJUAdapter(
            minimum_expected_chinese_programmes=3,
            minimum_expected_english_programmes=2,
            pdf_payload_fetcher=lambda url: PAYLOADS[url],
        ).parse_catalog_from_fetcher(_fetcher)
