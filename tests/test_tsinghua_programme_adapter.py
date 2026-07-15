from __future__ import annotations

import json

from gradwindow.programme_adapters.tsinghua import (
    APPLICATION_URL,
    CATALOG_URL,
    TsinghuaAdapter,
    catalog_query_url,
)

CATALOG_ID = "catalog-2026"
CATALOG_DETAIL_URL = (
    "https://yzbm.tsinghua.edu.cn/publish/s05/s0503/detail/catalog-2026/1"
)

LANDING_HTML = f"""
<main>
  <a href="/publish/s05/s0503/detail/catalog-2025/1">
    The Catalog of Master's Programs for International Students 2025
  </a>
  <a href="{CATALOG_DETAIL_URL}">
    The Catalog of Master's Programs for International Students 2026
  </a>
</main>
"""

DETAIL_HTML = """
<ul id="zsyx">
  <li data-value="024">Department of Computer Science and Technology</li>
  <li data-value="066">School of Law</li>
</ul>
"""

COMPUTER_PAYLOAD = {
    "code": 200,
    "datas": {
        "zsnd": "2026",
        "zsmlYxs": [
            {
                "zsyxsdm": "024",
                "zsyxsywmc": "Department of Computer Science and Technology",
                "zsyxsmc": "计算机科学与技术系",
                "exportZsmlYxZys": [
                    {
                        "zszydm": "081200",
                        "zszyywmc": "Computer Science and Technology",
                        "zszymc": "计算机科学与技术",
                        "exportZsmlYxZyYjfxs": [
                            {
                                "yjfxdm": "01",
                                "yjfxywmc": "Master in Advanced Computing(English)",
                                "yjfxmc": "先进计算英文硕士项目",
                                "xxfsywmc": "Full-time",
                                "sfqywxmyw": "English-taught",
                                "bmjssjyw": (
                                    "Application Deadline:2026-02-27 17:00:00"
                                ),
                                "bmsjms": (
                                    "第一批次：即日起—2025年12月15日17:00；"
                                    "第二批次：2026年01月01日8:00—"
                                    "2026年02月27日17:00"
                                ),
                            }
                        ],
                    }
                ],
            }
        ],
    },
}

LAW_PAYLOAD = {
    "code": 200,
    "datas": {
        "zsnd": "2026",
        "zsmlYxs": [
            {
                "zsyxsdm": "066",
                "zsyxsywmc": "School of Law",
                "zsyxsmc": "法学院",
                "exportZsmlYxZys": [
                    {
                        "zszydm": "035101",
                        "zszyywmc": "Law",
                        "zszymc": "法律",
                        "exportZsmlYxZyYjfxs": [
                            {
                                "yjfxdm": "01",
                                "yjfxywmc": "Master's Program in Chinese Law (LL.M.)",
                                "yjfxmc": "中国法硕士项目",
                                "xxfsywmc": "Full-time",
                                "sfqywxmyw": "English-taught",
                                "bmjssjyw": (
                                    "Application Deadline:2026-03-31 17:00:00"
                                ),
                                "bmsjms": "",
                            },
                            {
                                "yjfxdm": "02",
                                "yjfxywmc": "Juris Master (Part-time)",
                                "yjfxmc": "非全日制法律硕士",
                                "xxfsywmc": "Part-time",
                                "sfqywxmyw": None,
                                "bmjssjyw": (
                                    "Application Deadline:2026-05-31 17:00:00"
                                ),
                                "bmsjms": (
                                    "第一批次：2026年1月1日8:00至"
                                    "2026年3月31日17:00；"
                                    "第二批次：2026年4月7日8:00至"
                                    "2026年5月31日17:00"
                                ),
                            },
                        ],
                    }
                ],
            }
        ],
    },
}


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return LANDING_HTML
    if url == CATALOG_DETAIL_URL:
        return DETAIL_HTML
    if url == catalog_query_url(CATALOG_ID, "024"):
        return json.dumps(COMPUTER_PAYLOAD, ensure_ascii=False)
    if url == catalog_query_url(CATALOG_ID, "066"):
        return json.dumps(LAW_PAYLOAD, ensure_ascii=False)
    raise AssertionError(url)


def test_tsinghua_adapter_uses_latest_official_catalogue_and_all_departments() -> None:
    catalog = TsinghuaAdapter(
        minimum_expected_programmes=3,
        minimum_expected_schools=2,
    ).parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert [programme.name for programme in catalog.programmes] == [
        "Juris Master (Part-time)",
        "Master's Program in Advanced Computing",
        "Master's Program in Chinese Law (LL.M.)",
    ]
    advanced = catalog.programmes[1]
    assert advanced.id == "tsinghua-advanced-computing-master"
    assert advanced.application_url == APPLICATION_URL
    assert advanced.faculty == "Department of Computer Science and Technology"


def test_tsinghua_adapter_keeps_missing_openings_separate_from_exact_rounds() -> None:
    catalog = TsinghuaAdapter(
        minimum_expected_programmes=3,
        minimum_expected_schools=2,
    ).parse_catalog_from_fetcher(_fetcher)
    by_name = {programme.name: programme for programme in catalog.programmes}

    advanced = by_name["Master's Program in Advanced Computing"]
    assert advanced.parse_status == "incomplete"
    assert [
        (window.round, window.intake, window.opens_at, window.closes_at)
        for window in advanced.windows
    ] == [
        ("First application round", "Autumn 2026", None, "2025-12-15"),
        (
            "Second application round",
            "Autumn 2026",
            "2026-01-01",
            "2026-02-27",
        ),
    ]

    llm = by_name["Master's Program in Chinese Law (LL.M.)"]
    assert [(window.opens_at, window.closes_at) for window in llm.windows] == [
        (None, "2026-03-31")
    ]

    juris = by_name["Juris Master (Part-time)"]
    assert juris.parse_status == "parsed"
    assert [(window.opens_at, window.closes_at) for window in juris.windows] == [
        ("2026-01-01", "2026-03-31"),
        ("2026-04-07", "2026-05-31"),
    ]


def test_tsinghua_adapter_rejects_truncated_catalogue() -> None:
    try:
        TsinghuaAdapter(
            minimum_expected_programmes=4,
            minimum_expected_schools=2,
        ).parse_catalog_from_fetcher(_fetcher)
    except ValueError as exc:
        assert "only contained 3" in str(exc)
    else:
        raise AssertionError("Truncated Tsinghua catalogue was accepted")
