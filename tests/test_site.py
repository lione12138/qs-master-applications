from __future__ import annotations

import json

from gradwindow.site import build_site


def test_build_site_only_publishes_public_assets(tmp_path) -> None:
    index = build_site(tmp_path)
    assert index.exists()
    assert (tmp_path / "app.js").exists()
    assert (tmp_path / "status.js").exists()
    assert (tmp_path / "styles.css").exists()
    assert (tmp_path / ".nojekyll").exists()
    assert (tmp_path / "sources.html").exists()
    assert (tmp_path / "data" / "universities.json").exists()
    assert (tmp_path / "data" / "programs.json").exists()
    assert (tmp_path / "data" / "programme-groups.json").exists()
    assert (tmp_path / "data" / "applicant-categories.json").exists()
    assert (tmp_path / "data" / "window-policies.json").exists()
    assert (tmp_path / "data" / "coverage.json").exists()
    assert (tmp_path / "data" / "application-source-state.json").exists()
    assert (tmp_path / "data" / "predictions.json").exists()
    assert not (tmp_path / "scripts").exists()
    assert not (tmp_path / "data" / "ror-cache.json").exists()
    assert not (tmp_path / "data" / "admissions-overrides.json").exists()
    assert not (tmp_path / "data" / "review-queue.json").exists()
    assert not (tmp_path / "data" / "window-candidates.json").exists()
    assert not (tmp_path / "data" / "evidence").exists()
    assert (tmp_path / "sitemap.xml").exists()
    assert (tmp_path / "robots.txt").exists()
    assert (
        tmp_path
        / "university"
        / "university-of-cambridge"
        / "index.html"
    ).exists()
    assert (tmp_path / "country" / "united-kingdom" / "index.html").exists()
    assert (tmp_path / "deadline" / "2026-02" / "index.html").exists()


def test_built_site_has_complete_directory(tmp_path) -> None:
    build_site(tmp_path)
    payload = json.loads(
        (tmp_path / "data" / "universities.json").read_text(encoding="utf-8")
    )
    assert len(payload["universities"]) == 200
    assert "Sources &amp; Coverage" not in (tmp_path / "sources.html").read_text(
        encoding="utf-8"
    )
    assert "来源与覆盖" in (tmp_path / "sources.html").read_text(encoding="utf-8")
    assert "预测参考" in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "university-of-cambridge" in (
        tmp_path / "sitemap.xml"
    ).read_text(encoding="utf-8")
