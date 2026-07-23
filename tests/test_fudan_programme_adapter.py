from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.fudan import (
    APPLICATION_URL,
    CATALOG_URL,
    CHINESE_CATALOG_LIST_URL,
    GRADUATE_LIST_URL,
    FudanAdapter,
    catalog_page_url,
)

CATALOG_PAGE_ONE = """
<main>
  <span class="all_pages">2</span>
  <ul class="news_list">
    <li><span class="news_title"><a
      href="/isoenglish/f2/76/c52434a782966/page.htm"
      title="Doctoral Program in International Politics (DPIP)"
    >Doctoral Program in International Politics</a></span></li>
    <li><span class="news_title"><a
      href="/isoenglish/f2/7d/c52434a782973/page.htm"
      title="Master Program in Global Public Policy"
    >Master Program in Global Public Policy</a></span></li>
    <li><span class="news_title"><a
      href="/isoenglish/f2/86/c52434a782982/page.htm"
      title="FLS LL.M. Program in Chinese Business Law"
    >FLS LL.M. Program in Chinese Business Law</a></span></li>
  </ul>
</main>
"""

CATALOG_PAGE_TWO = """
<main>
  <ul class="news_list">
    <li><span class="news_title"><a
      href="/isoenglish/f2/90/c52434a782992/page.htm"
      title="Fudan-LSE Double Degree in Global Social Policy"
    >Fudan-LSE Double Degree in Global Social Policy</a></span></li>
    <li><span class="news_title"><a
      href="/isoenglish/f2/99/c52434a783001/page.htm"
      title="2026 Bachelor of Medicine and Bachelor of Surgery (MBBS) (English-taught)"
    >2026 MBBS</a></span></li>
  </ul>
</main>
"""

GRADUATE_LIST = """
<main>
  <a href="/isoenglish/old/page.htm"
     title="2025 Admission Information on English-taught Postgraduate Programs at Fudan University">
    2025 admissions
  </a>
  <a href="/isoenglish/7b/e4/c51328a752612/page.htm"
     title="2026 Admission Information on English-taught Postgraduate Programs at Fudan University">
    2026 admissions
  </a>
</main>
"""

ADMISSIONS_ARTICLE = """
<main>
  <div class="wp_pdf_player"
       pdfsrc="/_upload/article/files/current/fudan-2026-admissions.pdf"
       sudyfile-attr="{'title':'2026 Admission Information on English-taught Postgraduate Programs at Fudan University.pdf'}">
  </div>
</main>
"""

ADMISSIONS_TEXT = """
2026 Admission Information on English-taught Postgraduate Programs
Fudan University
Application Period
Phase One: From October 13, 2025 to December 12, 2025
Phase Two: From March 1, 2026 to March 31, 2026
Enrollment Time
The date of enrollment is in late August or early September 2026.
"""

CHINESE_CATALOG_LIST = """
<main>
  <a href="/_upload/article/files/current/fudan-2026-chinese-master.xlsx"
     title="2026年复旦大学外国留学生中文授课硕士研究生招生专业目录">
    中文授课硕士研究生招生专业目录
  </a>
  <a href="/73/91/c16063a750481/page.htm"
     title="2026年复旦大学外国留学生研究生中文授课项目招生简章">
    中文授课项目招生简章
  </a>
</main>
"""

CHINESE_CATALOG_PAYLOAD = json.dumps(
    {
        "worksheets": [
            {
                "name": "硕士中文招生专业",
                "rows": [
                    ["2026年复旦大学外国留学生中文授课硕士研究生招生专业目录"],
                    ["序号", "院系名称", "专业名称", "专业方向", "学制"],
                    [
                        1,
                        "数学科学学院",
                        "（学术学位）数学",
                        "（全日制）基础数学",
                        "3年",
                    ],
                    [2, None, None, "（全日制）应用数学", "3年"],
                    [
                        3,
                        "大数据学院",
                        "（专业学位）应用统计",
                        "（全日制）数据科学",
                        "2年",
                    ],
                ],
            }
        ]
    },
    ensure_ascii=False,
)

CHINESE_ADMISSIONS_ARTICLE = """
<main>
  <div class="wp_pdf_player"
       pdfsrc="/_upload/article/files/current/fudan-2026-chinese-admissions.pdf"
       sudyfile-attr="{'title':'2026年复旦大学外国留学生研究生招生简章（中文授课）.pdf'}">
  </div>
</main>
"""

CHINESE_ADMISSIONS_TEXT = """
2026年复旦大学外国留学生研究生中文授课项目招生简章
二、申请时间
第一阶段：2025 年 10 月 13 日至 2025 年 12 月 12 日
第二阶段：2026 年 03 月 01 日至 2026 年 03 月 31 日
"""

ADMISSIONS_PAGE_URL = "https://iso.fudan.edu.cn/isoenglish/7b/e4/c51328a752612/page.htm"
ADMISSIONS_PDF_URL = (
    "https://iso.fudan.edu.cn/_upload/article/files/current/fudan-2026-admissions.pdf"
)
CHINESE_CATALOG_XLSX_URL = (
    "https://iso.fudan.edu.cn/_upload/article/files/current/"
    "fudan-2026-chinese-master.xlsx"
)
CHINESE_ADMISSIONS_PAGE_URL = "https://iso.fudan.edu.cn/73/91/c16063a750481/page.htm"
CHINESE_ADMISSIONS_PDF_URL = (
    "https://iso.fudan.edu.cn/_upload/article/files/current/"
    "fudan-2026-chinese-admissions.pdf"
)


def _pages() -> dict[str, str]:
    return {
        CATALOG_URL: CATALOG_PAGE_ONE,
        catalog_page_url(2): CATALOG_PAGE_TWO,
        GRADUATE_LIST_URL: GRADUATE_LIST,
        ADMISSIONS_PAGE_URL: ADMISSIONS_ARTICLE,
        ADMISSIONS_PDF_URL: ADMISSIONS_TEXT,
        CHINESE_CATALOG_LIST_URL: CHINESE_CATALOG_LIST,
        CHINESE_CATALOG_XLSX_URL: CHINESE_CATALOG_PAYLOAD,
        CHINESE_ADMISSIONS_PAGE_URL: CHINESE_ADMISSIONS_ARTICLE,
        CHINESE_ADMISSIONS_PDF_URL: CHINESE_ADMISSIONS_TEXT,
    }


def _adapter(*, english: int = 3, chinese: int = 2) -> FudanAdapter:
    return FudanAdapter(
        minimum_expected_english_programmes=english,
        minimum_expected_chinese_programmes=chinese,
    )


def test_fudan_adapter_discovers_only_official_english_taught_masters() -> None:
    pages = _pages()
    catalog = _adapter().parse_catalog_from_fetcher(lambda url: pages[url])
    english = [
        programme
        for programme in catalog.programmes
        if not programme.id.startswith("fudan-cn-master-")
    ]

    assert catalog.application_opens_at is None
    assert [programme.id for programme in english] == [
        "fudan-fls-ll-m-program-in-chinese-business-law",
        "fudan-fudan-lse-double-degree-in-global-social-policy",
        "fudan-master-program-in-global-public-policy",
    ]
    assert [programme.degree_type for programme in english] == [
        "LLM",
        "Master",
        "Master",
    ]
    assert all("Doctoral" not in programme.name for programme in english)
    assert all("Bachelor" not in programme.name for programme in english)


def test_fudan_adapter_applies_the_official_two_phase_2026_policy() -> None:
    pages = _pages()
    catalog = _adapter().parse_catalog_from_fetcher(lambda url: pages[url])
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "fudan-master-program-in-global-public-policy"
    )

    assert programme.application_url == APPLICATION_URL
    assert programme.parse_status == "parsed"
    assert [window.round for window in programme.windows] == [
        "Phase One",
        "Phase Two",
    ]
    assert [window.intake for window in programme.windows] == [
        "Autumn 2026",
        "Autumn 2026",
    ]
    assert [window.opens_at for window in programme.windows] == [
        "2025-10-13",
        "2026-03-01",
    ]
    assert [window.closes_at for window in programme.windows] == [
        "2025-12-12",
        "2026-03-31",
    ]
    assert all(
        window.applicant_categories == ["international-students"]
        for window in programme.windows
    )
    assert all(window.source_url == ADMISSIONS_PDF_URL for window in programme.windows)
    assert "2025-10-13 to 2025-12-12" in programme.deadline_text


def test_fudan_adapter_parses_and_deduplicates_chinese_taught_xlsx() -> None:
    pages = _pages()
    catalog = _adapter().parse_catalog_from_fetcher(lambda url: pages[url])
    chinese = [
        programme
        for programme in catalog.programmes
        if programme.id.startswith("fudan-cn-master-")
    ]

    assert len(chinese) == 2
    assert {programme.name for programme in chinese} == {
        "数学（中文授课）",
        "应用统计（中文授课）",
    }
    assert {programme.faculty for programme in chinese} == {
        "数学科学学院",
        "大数据学院",
    }
    assert {programme.degree_type for programme in chinese} == {
        "Academic Master",
        "Professional Master",
    }
    assert all(len(programme.windows) == 2 for programme in chinese)
    assert all(
        window.source_url == CHINESE_ADMISSIONS_PDF_URL
        for programme in chinese
        for window in programme.windows
    )


def test_fudan_adapter_rejects_a_truncated_english_catalogue() -> None:
    pages = _pages()
    with pytest.raises(ValueError, match="English-taught catalogue only contained 3"):
        _adapter(english=4).parse_catalog_from_fetcher(lambda url: pages[url])


def test_fudan_adapter_rejects_a_truncated_chinese_catalogue() -> None:
    pages = _pages()
    with pytest.raises(ValueError, match="Chinese-taught catalogue only contained 2"):
        _adapter(chinese=3).parse_catalog_from_fetcher(lambda url: pages[url])


def test_fudan_adapter_rejects_a_brochure_without_two_exact_phases() -> None:
    pages = _pages()
    pages[ADMISSIONS_PDF_URL] = "Applications run from October to March."

    with pytest.raises(ValueError, match="two exact application phases"):
        _adapter().parse_catalog_from_fetcher(lambda url: pages[url])


def test_fudan_adapter_uses_current_official_iso_sources() -> None:
    assert CATALOG_URL == (
        "https://iso.fudan.edu.cn/isoenglish/EnglishwTaughtProgram/list.htm"
    )
    assert GRADUATE_LIST_URL == "https://iso.fudan.edu.cn/isoenglish/51328/list.htm"
    assert CHINESE_CATALOG_LIST_URL == "https://iso.fudan.edu.cn/16063/list.htm"
    assert catalog_page_url(3) == (
        "https://iso.fudan.edu.cn/isoenglish/EnglishwTaughtProgram/list3.htm"
    )
