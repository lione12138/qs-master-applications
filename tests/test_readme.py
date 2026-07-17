from __future__ import annotations

from datetime import date

from gradwindow.readme import generate_readmes


def test_generate_bilingual_result_readmes(monkeypatch, tmp_path) -> None:
    english = tmp_path / "README.md"
    chinese = tmp_path / "README.zh-CN.md"
    monkeypatch.setattr("gradwindow.readme.README_PATH", english)
    monkeypatch.setattr("gradwindow.readme.README_ZH_PATH", chinese)

    generate_readmes(date(2026, 6, 15))

    english_text = english.read_text(encoding="utf-8")
    chinese_text = chinese.read_text(encoding="utf-8")
    assert "docs/readme-hero.svg" in english_text
    assert "github/stars/lione12138/qs-master-applications" in english_text
    assert "<strong>200</strong> universities" in english_text
    assert "Built for trust, not deadline spam" in english_text
    assert "<details>" in english_text
    assert "## Open Now" in english_text
    assert "## Opening Within 30 Days" in english_text
    assert '<a href="README.zh-CN.md">简体中文</a>' in english_text
    assert "[Code](LICENSE)" in english_text
    assert "[data](DATA_LICENSE.md)" in english_text
    assert "CC BY-NC 4.0" in english_text
    assert english_text.index("leave a ⭐") > english_text.index(
        "## Live deadline snapshot"
    )
    assert "## 正在开放" in chinese_text
    assert "## 30 天内即将开放" in chinese_text
    assert '<a href="README.md">English</a>' in chinese_text
    assert "[代码](LICENSE)" in chinese_text
    assert "[数据](DATA_LICENSE.md)" in chinese_text
    assert "QS Top 200" in english_text
    assert "宁可少，也不要未经核验的截止日期" in chinese_text
    assert "点一颗 ⭐" in chinese_text
