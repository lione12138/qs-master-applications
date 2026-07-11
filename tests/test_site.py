from __future__ import annotations

import json
from pathlib import Path

import pytest

import gradwindow.site as site
from gradwindow.paths import SITE_DIR
from gradwindow.site import build_site

ANALYTICS_BEACON = "https://static.cloudflareinsights.com/beacon.min.js"


@pytest.mark.parametrize("target_name", ["root", "ancestor", "src", "data"])
def test_build_site_rejects_dangerous_output_paths(
    tmp_path,
    monkeypatch,
    target_name,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    fake_site_dir = project_root / "site"
    targets = {
        "root": project_root,
        "ancestor": tmp_path,
        "src": project_root / "src",
        "data": project_root / "data",
    }
    target = targets[target_name]
    target.mkdir(parents=True, exist_ok=True)
    marker = target / "must-not-be-deleted.txt"
    marker.write_text("source data", encoding="utf-8")
    monkeypatch.setattr(site, "ROOT", project_root)
    monkeypatch.setattr(site, "SITE_DIR", fake_site_dir)

    with pytest.raises(ValueError, match="Refusing to build"):
        build_site(target)

    assert marker.read_text(encoding="utf-8") == "source data"


def test_build_site_accepts_default_site_directory() -> None:
    assert site._safe_build_output_dir(SITE_DIR) == SITE_DIR.resolve()


def test_build_site_only_publishes_public_assets(tmp_path) -> None:
    index = build_site(tmp_path)
    assert index.exists()
    assert (tmp_path / "app.js").exists()
    assert (tmp_path / "status.js").exists()
    assert (tmp_path / "intake-filter.js").exists()
    assert (tmp_path / "ranking-filter.js").exists()
    assert (tmp_path / "window-grouping.js").exists()
    assert (tmp_path / "localization.js").exists()
    assert (tmp_path / "i18n.js").exists()
    assert (tmp_path / "privacy.html").exists()
    assert (tmp_path / "roadmap.html").exists()
    assert (tmp_path / "roadmap.js").exists()
    assert (tmp_path / "styles.css").exists()
    assert (tmp_path / "og-image.png").exists()
    assert (tmp_path / "favicon.svg").exists()
    assert (tmp_path / "CNAME").read_text(encoding="utf-8").strip() == "gradwindow.com"
    assert (tmp_path / ".nojekyll").exists()
    assert (tmp_path / "sources.html").exists()
    assert (tmp_path / "data" / "universities.json").exists()
    assert (tmp_path / "data" / "programs.json").exists()
    assert (tmp_path / "data" / "programme-groups.json").exists()
    assert (tmp_path / "data" / "applicant-categories.json").exists()
    assert (tmp_path / "data" / "window-policies.json").exists()
    assert (tmp_path / "data" / "coverage.json").exists()
    assert (tmp_path / "data" / "global-rankings.json").exists()
    assert (tmp_path / "data" / "application-source-state.json").exists()
    assert (tmp_path / "data" / "roadmap-proposals.json").exists()
    assert (tmp_path / "data" / "predictions.json").exists()
    assert not (tmp_path / "scripts").exists()
    assert not (tmp_path / "data" / "ror-cache.json").exists()
    assert not (tmp_path / "data" / "admissions-overrides.json").exists()
    assert not (tmp_path / "data" / "review-queue.json").exists()
    assert not (tmp_path / "data" / "window-candidates.json").exists()
    assert not (tmp_path / "data" / "evidence").exists()
    assert (tmp_path / "sitemap.xml").exists()
    assert (tmp_path / "robots.txt").exists()
    assert (tmp_path / "university" / "university-of-cambridge" / "index.html").exists()
    assert (tmp_path / "country" / "united-kingdom" / "index.html").exists()
    assert (tmp_path / "deadline" / "2026-02" / "index.html").exists()


def test_cloudflare_worker_build_has_a_static_assets_entrypoint() -> None:
    config = json.loads(
        (Path(__file__).resolve().parents[1] / "wrangler.jsonc").read_text(
            encoding="utf-8"
        )
    )

    assert config["name"] == "qs-master-applications"
    assert config["build"]["command"] == "python -m gradwindow.cli build-site"
    assert config["assets"]["directory"] == "./site"


def test_built_site_has_complete_directory(tmp_path) -> None:
    build_site(tmp_path)
    payload = json.loads(
        (tmp_path / "data" / "universities.json").read_text(encoding="utf-8")
    )
    assert len(payload["universities"]) == 200
    sources_html = (tmp_path / "sources.html").read_text(encoding="utf-8")
    assert "Sources and coverage" in sources_html
    assert 'lang="en"' in sources_html
    assert 'rel="canonical" href="https://gradwindow.com/sources.html"' in sources_html
    assert 'property="og:image"' in sources_html
    assert '"@type": "BreadcrumbList"' in sources_html
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'data-status="predicted"' not in index_html
    assert 'id="language-toggle"' in index_html
    assert 'id="theme-toggle"' in index_html
    assert 'id="ranking-filter"' in index_html
    assert 'id="rank-range-filter"' in index_html
    assert 'class="mobile-dashboard-intro"' in index_html
    assert 'class="mobile-sort-controls"' in index_html
    assert 'class="hero-visual"' in index_html
    assert 'class="hero-dashboard"' not in index_html
    assert 'class="quick-filter-panel"' in index_html
    assert 'class="tracker-workspace"' in index_html
    assert 'class="tracker-sidebar"' in index_html
    assert 'class="tracker-results"' in index_html
    assert 'id="hero-open-count"' in index_html
    assert 'id="hero-deadline-day"' in index_html
    assert 'id="hero-deadline-month"' in index_html
    assert 'id="mobile-filter-toggle"' in index_html
    assert 'id="window-detail-panel"' in index_html
    assert 'class="mobile-bottom-nav"' in index_html
    assert 'id="sort-select"' not in index_html
    assert 'id="top100-toggle"' not in index_html
    assert 'id="coverage-batches"' not in index_html
    assert 'lang="en"' in index_html
    assert 'property="og:image"' in index_html
    assert "og-image.png" in index_html
    assert (
        'name="robots" content="index, follow, max-image-preview:large"' in index_html
    )
    assert 'rel="modulepreload"' in index_html
    assert "application/ld+json" in index_html
    assert "Source code" in index_html
    assert "AGPL-3.0" in index_html
    assert "Data: CC BY-NC 4.0" in index_html
    assert index_html.count(ANALYTICS_BEACON) == 1
    app_js = (tmp_path / "app.js").read_text(encoding="utf-8")
    styles_css = (tmp_path / "styles.css").read_text(encoding="utf-8")
    assert "openWindowDetail(record" in app_js
    assert 'id="hero-deadline-countdown"' not in index_html
    assert "data-mobile-sort" in index_html
    assert ".window-card-row" in styles_css
    assert 'row.className = "university-card-row"' in app_js
    assert ".university-table tr.university-card-row" in styles_css
    assert 'body[data-view-status="unknown"] .mobile-sort-controls' in styles_css
    assert ".mobile-bottom-nav" in styles_css
    assert "grid-template-columns: 268px minmax(0, 1fr)" in styles_css
    assert ".tracker-results .application-table tbody tr" in styles_css
    assert "height: 76px" in styles_css
    assert (tmp_path / "sources.html").read_text(encoding="utf-8").count(
        ANALYTICS_BEACON
    ) == 1
    assert (
        tmp_path / "university" / "university-of-cambridge" / "index.html"
    ).read_text(encoding="utf-8").count(ANALYTICS_BEACON) == 1
    university_html = (
        tmp_path / "university" / "university-of-cambridge" / "index.html"
    ).read_text(encoding="utf-8")
    assert '"@type": "WebPage"' in university_html
    assert '"@type": "BreadcrumbList"' in university_html
    assert 'property="og:image"' in university_html
    assert 'aria-label="GradWindow pages"' in university_html
    assert (tmp_path / "country" / "united-kingdom" / "index.html").read_text(
        encoding="utf-8"
    ).count(ANALYTICS_BEACON) == 1
    assert (tmp_path / "deadline" / "2026-02" / "index.html").read_text(
        encoding="utf-8"
    ).count(ANALYTICS_BEACON) == 1
    assert "university-of-cambridge" in (tmp_path / "sitemap.xml").read_text(
        encoding="utf-8"
    )
    assert "roadmap.html" in (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    contact_html = (tmp_path / "contact.html").read_text(encoding="utf-8")
    assert 'action="mailto:' not in contact_html
    assert 'id="contact-subject"' in contact_html
    for page_name in (
        "calendar.html",
        "contact.html",
        "roadmap.html",
        "privacy.html",
    ):
        page_html = (tmp_path / page_name).read_text(encoding="utf-8")
        assert 'rel="canonical"' in page_html
        assert 'property="og:image"' in page_html
        assert 'type="application/ld+json"' in page_html


def test_build_site_uses_configured_public_url(tmp_path, monkeypatch) -> None:
    public_url = "https://gradwindow.pages.dev"
    monkeypatch.setenv("GRADWINDOW_SITE_URL", public_url)

    build_site(tmp_path)

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    sitemap = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    robots = (tmp_path / "robots.txt").read_text(encoding="utf-8")
    university_page = (
        tmp_path / "university" / "university-of-cambridge" / "index.html"
    ).read_text(encoding="utf-8")

    assert f'href="{public_url}/"' in index_html
    assert f"<loc>{public_url}</loc>" in sitemap
    assert f"Sitemap: {public_url}/sitemap.xml" in robots
    assert f'href="{public_url}/university/university-of-cambridge/"' in university_page
    for page_name in (
        "calendar.html",
        "contact.html",
        "roadmap.html",
        "privacy.html",
        "sources.html",
    ):
        page_html = (tmp_path / page_name).read_text(encoding="utf-8")
        assert public_url in page_html
        assert "https://gradwindow.com/" not in page_html


def test_build_site_injects_private_subscription_endpoint(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "GRADWINDOW_SUBSCRIBE_URL",
        "https://subscriptions.example.workers.dev",
    )
    monkeypatch.setenv("GRADWINDOW_TURNSTILE_SITE_KEY", "public-site-key")

    build_site(tmp_path)

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '"subscribeUrl": "https://subscriptions.example.workers.dev"' in index_html
    assert '"turnstileSiteKey": "public-site-key"' in index_html
    assert "EMAIL_ENCRYPTION_KEY" not in index_html


def test_build_site_injects_roadmap_endpoint_into_roadmap_page(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRADWINDOW_ROADMAP_URL", "https://api.example.workers.dev")
    monkeypatch.setenv("GRADWINDOW_TURNSTILE_SITE_KEY", "public-site-key")

    build_site(tmp_path)

    roadmap_html = (tmp_path / "roadmap.html").read_text(encoding="utf-8")
    roadmap_js = (tmp_path / "roadmap.js").read_text(encoding="utf-8")
    assert '"roadmapUrl": "https://api.example.workers.dev"' in roadmap_html
    assert '"turnstileSiteKey": "public-site-key"' in roadmap_html
    assert 'data-action", "turnstile-spin-v1"' in roadmap_js
    assert "roadmapTurnstileError" in roadmap_js
    assert "EMAIL_ENCRYPTION_KEY" not in roadmap_html
