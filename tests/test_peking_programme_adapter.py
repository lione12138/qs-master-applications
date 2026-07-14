from __future__ import annotations

import json

from gradwindow.programme_adapters.peking import (
    APPLICATION_URL,
    CATALOG_URL,
    PekingAdapter,
    _date_ranges,
)

STANDARD_GUIDE = "https://www.isd.pku.edu.cn/cn/detail.php?id=725"
COMPUTER_GUIDE = "https://www.isd.pku.edu.cn/cn/detail.php?id=739"
YENCHING_GUIDE = "https://www.isd.pku.edu.cn/en/detail.php?id=756"

CATALOG = {
    "code": 1,
    "msg": "数据获取成功",
    "info": {
        "list": [
            {
                "id": "1",
                "departmentid": "10",
                "major": "计算机科学与技术",
                "direction": "计算理论",
                "learningstyle": "1",
                "language": "1",
                "degreetype": "1",
                "department_name": "计算机学院",
                "language_text": "中文",
                "learningstyle_text": "全日制",
                "degreetype_text": "硕士",
                "recruitment1": STANDARD_GUIDE,
            },
            {
                "id": "2",
                "departmentid": "10",
                "major": "计算机科学与技术",
                "direction": "软件工程",
                "learningstyle": "1",
                "language": "1",
                "degreetype": "1",
                "department_name": "计算机学院",
                "language_text": "中文",
                "learningstyle_text": "全日制",
                "degreetype_text": "硕士",
                "recruitment1": STANDARD_GUIDE,
            },
            {
                "id": "3",
                "departmentid": "10",
                "major": "计算机科学与技术",
                "direction": "人工智能",
                "learningstyle": "1",
                "language": "2",
                "degreetype": "1",
                "department_name": "计算机学院",
                "language_text": "英文",
                "learningstyle_text": "全日制",
                "degreetype_text": "硕士",
                "recruitment1": COMPUTER_GUIDE,
            },
            {
                "id": "4",
                "departmentid": "28",
                "major": "中国学（哲学与宗教）",
                "direction": "不区分研究方向",
                "learningstyle": "1",
                "language": "2",
                "degreetype": "1",
                "department_name": "燕京学堂",
                "language_text": "英文",
                "learningstyle_text": "全日制",
                "degreetype_text": "硕士",
                "recruitment1": YENCHING_GUIDE,
            },
            {
                "id": "5",
                "departmentid": "28",
                "major": "中国学（经济与管理）",
                "direction": "不区分研究方向",
                "learningstyle": "1",
                "language": "2",
                "degreetype": "1",
                "department_name": "燕京学堂",
                "language_text": "英文",
                "learningstyle_text": "全日制",
                "degreetype_text": "硕士",
                "recruitment1": YENCHING_GUIDE,
            },
            {
                "id": "6",
                "departmentid": "10",
                "major": "计算机科学与技术",
                "direction": "机器学习",
                "learningstyle": "1",
                "language": "2",
                "degreetype": "2",
                "department_name": "计算机学院",
                "language_text": "英文",
                "learningstyle_text": "全日制",
                "degreetype_text": "博士",
                "recruitment1": COMPUTER_GUIDE,
            },
        ]
    },
}

STANDARD_HTML = """
<main>
  <p>四、申请时间（北京时间）</p>
  <p>2025 年10月20日至2025年12月23日</p>
  <p>注：各英文授课硕士项目的申请截止日期见相应招生说明。</p>
</main>
"""

COMPUTER_HTML = """
<main>
  <p>Application Period (Beijing time)</p>
  <p>Chinese-taught Program: October 20, 2025 - December 23, 2025</p>
  <p>English-taught Program: October 20, 2025 - January 10, 2026</p>
</main>
"""

YENCHING_HTML = """
<main>
  <p>Application for the 2026 cohort is open on September 10 until
  December 1, 2025.</p>
</main>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return json.dumps(CATALOG, ensure_ascii=False)
    if url == STANDARD_GUIDE:
        return STANDARD_HTML
    if url == COMPUTER_GUIDE:
        return COMPUTER_HTML
    if url == YENCHING_GUIDE:
        return YENCHING_HTML
    raise AssertionError(url)


def test_peking_adapter_deduplicates_directions_and_keeps_language_variants() -> None:
    catalog = PekingAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert len(catalog.programmes) == 3
    assert catalog.application_opens_at is None
    assert [programme.name for programme in catalog.programmes] == [
        "Yenching Academy Master's in China Studies",
        "计算机科学与技术（中文授课）",
        "计算机科学与技术（英文授课）",
    ]
    assert catalog.programmes[0].id == "pku-yenching-china-studies-master"
    assert catalog.programmes[1].application_url == APPLICATION_URL


def test_peking_adapter_uses_only_fully_explicit_official_date_ranges() -> None:
    catalog = PekingAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )
    by_name = {programme.name: programme for programme in catalog.programmes}

    chinese = by_name["计算机科学与技术（中文授课）"]
    assert chinese.parse_status == "parsed"
    assert [
        (window.opens_at, window.closes_at, window.applicant_categories)
        for window in chinese.windows
    ] == [("2025-10-20", "2025-12-23", ["international-students"])]

    english = by_name["计算机科学与技术（英文授课）"]
    assert english.windows[0].opens_at == "2025-10-20"
    assert english.windows[0].closes_at == "2026-01-10"

    yenching = by_name["Yenching Academy Master's in China Studies"]
    assert yenching.windows == []
    assert yenching.parse_status == "no-deadline"
    assert "opening year is not explicit" in yenching.deadline_text


def test_peking_adapter_rejects_a_truncated_or_invalid_catalogue() -> None:
    try:
        PekingAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
            _fetcher
        )
    except ValueError as exc:
        assert "only contained 3" in str(exc)
    else:
        raise AssertionError("Truncated Peking catalogue was accepted")


def test_peking_date_ranges_select_the_nearest_language_label() -> None:
    text = (
        "Chinese-taught Program: October 20, 2025 - December 23, 2025 "
        "English-taught Program: October 20, 2025 - January 10, 2026"
    )

    assert _date_ranges(text, "中文") == [("2025-10-20", "2025-12-23")]
    assert _date_ranges(text, "英文") == [("2025-10-20", "2026-01-10")]
