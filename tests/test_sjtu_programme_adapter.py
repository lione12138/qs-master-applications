from __future__ import annotations

import pytest

from gradwindow.programme_adapters.sjtu import (
    APPLICATION_URL,
    CATALOG_URL,
    CHINESE_CATALOG_URL,
    ENGLISH_CATALOG_URL,
    SJTUAdapter,
)

GUIDE_2027 = f"""
<html><body>
  <h1>上海交通大学2027年国际研究生招生简章</h1>
  <p>申请时间（北京时间）：</p>
  <p>2026年10月15日 开放报名</p>
  <p>2026年12月15日 中国政府奖学金第一轮申请截止（通过高校申请）</p>
  <p>2027年2月15日 中国政府奖学金申请截止（通过高校申请）</p>
  <p>2027年3月31日 上海市政府奖学金、学校奖学金申请截止</p>
  <p>2027年5月31日 自费生申请截止</p>
  <p>入学时间为2027年9月。</p>
  <a href="{CHINESE_CATALOG_URL}">上海交通大学2027年硕士留学生招生中文授课专业目录</a>
  <a href="{ENGLISH_CATALOG_URL}">上海交通大学2027年硕士留学生招生英文授课专业目录</a>
</body></html>
"""

GUIDE_2026 = (
    GUIDE_2027.replace("2027年国际", "2026年国际")
    .replace("2027年硕士", "2026年硕士")
    .replace("2026年10月15日", "2025年10月15日")
    .replace("2026年12月15日", "2025年12月15日")
    .replace("2027年", "2026年")
)

CHINESE_CATALOG = """
上海交通大学 2027 年国际硕士研究生招生中文授课专业目录
SJTU 2027 Master Programs in Chinese for International Students
010
船舶海洋与建筑工程学院
School of Ocean
and Civil Engineering
081400 土木工程
Civil Engineering
岩土工程 Geotechnical Engineering
033
计算机学院
School of Computer Science
081200
计算机科学与技术
Computer
Science and
Technology
计算机系统结构 Computer System Structure
120
安泰经济与管理学院
Antai College of Economics and Management
125100
工商管理硕士
Master of Business Administration
中国全球运营领袖
CLGO Program - Full-time
1258S1
技术转移硕士
Master of Technology Transfer
科技成果转化 Technology Commercialisation
"""

ENGLISH_CATALOG = """
上海交通大学 2027 年国际硕士研究生招生英文授课专业目录
SJTU 2027 Master Programs in English for International Students
010
船舶海洋与建筑工程学院
School of Ocean and Civil Engineering
081400 土木工程
Civil Engineering
结构工程 Structural Engineering
033
计算机学院
School of Computer Science
081200
计算机科学与技术
Computer Science and
Technology
计算机科学与技术 Computer Science and Technology
490 溥渊未来技术学院
Global Institute of Future Technology
085800 能源动力 Energy and
Power Engineering
未来能源技术 Future Energy Technologies
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return GUIDE_2027
    if url == CHINESE_CATALOG_URL:
        return CHINESE_CATALOG
    if url == ENGLISH_CATALOG_URL:
        return ENGLISH_CATALOG
    raise AssertionError(url)


def _adapter() -> SJTUAdapter:
    return SJTUAdapter(
        minimum_expected_chinese_programmes=4,
        minimum_expected_english_programmes=3,
        target_intake_year=2027,
    )


def test_sjtu_adapter_discovers_both_official_master_catalogues() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 7
    assert len({programme.id for programme in catalog.programmes}) == 7
    assert {programme.source_url for programme in catalog.programmes} == {
        CHINESE_CATALOG_URL,
        ENGLISH_CATALOG_URL,
    }
    assert all(
        programme.application_url == APPLICATION_URL for programme in catalog.programmes
    )


def test_sjtu_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "sjtu-computer-science-technology-master"
    )

    assert programme.name == "Master in Computer Science and Technology"
    assert programme.faculty == "School of Computer Science"
    assert programme.source_url == ENGLISH_CATALOG_URL


def test_sjtu_adapter_keeps_catalogue_languages_and_alphanumeric_codes_distinct() -> (
    None
):
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    civil = [item for item in catalog.programmes if "Civil Engineering" in item.name]
    technology_transfer = next(
        item for item in catalog.programmes if "Technology Transfer" in item.name
    )

    assert len(civil) == 2
    assert {item.name for item in civil} == {
        "Master in Civil Engineering (Chinese-taught)",
        "Master in Civil Engineering (English-taught)",
    }
    assert "1258s1" in technology_transfer.id


def test_sjtu_adapter_parses_exact_fall_2027_international_windows() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if "Civil Engineering" in item.name
    )

    assert [
        (window.round, window.opens_at, window.closes_at, window.intake)
        for window in programme.windows
    ] == [
        (
            "Chinese Government Scholarship first round",
            "2026-10-15",
            "2026-12-15",
            "Fall 2027",
        ),
        (
            "Chinese Government Scholarship",
            "2026-10-15",
            "2027-02-15",
            "Fall 2027",
        ),
        (
            "Shanghai Government/SJTU Scholarship",
            "2026-10-15",
            "2027-03-31",
            "Fall 2027",
        ),
        ("Self-funded", "2026-10-15", "2027-05-31", "Fall 2027"),
    ]
    assert all(window.source_url == CATALOG_URL for window in programme.windows)
    assert programme.parse_status == "parsed"


def test_sjtu_adapter_filters_the_stale_2026_cycle() -> None:
    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return GUIDE_2026
        if url == CHINESE_CATALOG_URL:
            return CHINESE_CATALOG.replace("2027", "2026")
        if url == ENGLISH_CATALOG_URL:
            return ENGLISH_CATALOG.replace("2027", "2026")
        return _fetcher(url)

    catalog = _adapter().parse_catalog_from_fetcher(fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "2026 intake" in programme.deadline_text for programme in catalog.programmes
    )


def test_sjtu_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="Chinese-taught catalogue only contained 4"):
        SJTUAdapter(
            minimum_expected_chinese_programmes=5,
            minimum_expected_english_programmes=3,
            target_intake_year=2027,
        ).parse_catalog_from_fetcher(_fetcher)
