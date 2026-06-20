from __future__ import annotations

import html
import json
import os
import re
import shutil
from pathlib import Path

from .io import read_json
from .paths import (
    APPLICANT_CATEGORIES_PATH,
    APPLICATIONS_PATH,
    APPLICATION_SOURCE_STATE_PATH,
    COVERAGE_PATH,
    MONITOR_STATE_PATH,
    PREDICTIONS_PATH,
    ROOT,
    SITE_DIR,
    PROGRAMS_PATH,
    PROGRAMME_GROUPS_PATH,
    UNIVERSITIES_PATH,
    WINDOW_POLICIES_PATH,
)

PUBLIC_FILES = (
    "index.html",
    "calendar.html",
    "contact.html",
    "roadmap.html",
    "privacy.html",
    "app.js",
    "calendar.js",
    "contact.js",
    "roadmap.js",
    "exception-status.js",
    "status.js",
    "intake-filter.js",
    "localization.js",
    "i18n.js",
    "styles.css",
    "og-image.png",
    "favicon.svg",
)
DEFAULT_SITE_URL = "https://lione12138.github.io/qs-master-applications"
CLOUDFLARE_ANALYTICS_TOKEN = "02939949076c423f953d11db0caade78"
CLOUDFLARE_ANALYTICS = (
    '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
    f"data-cf-beacon='{{\"token\":\"{CLOUDFLARE_ANALYTICS_TOKEN}\"}}'>"
    "</script>"
)
PUBLIC_DATA = (
    UNIVERSITIES_PATH,
    APPLICATIONS_PATH,
    PREDICTIONS_PATH,
    MONITOR_STATE_PATH,
    PROGRAMS_PATH,
    PROGRAMME_GROUPS_PATH,
    APPLICANT_CATEGORIES_PATH,
    WINDOW_POLICIES_PATH,
    COVERAGE_PATH,
    APPLICATION_SOURCE_STATE_PATH,
    ROOT / "data" / "roadmap-proposals.json",
)


def site_url() -> str:
    return os.environ.get("GRADWINDOW_SITE_URL", DEFAULT_SITE_URL).rstrip("/")


def build_site(output_dir: Path = SITE_DIR) -> Path:
    public_site_url = site_url()
    public_config = {
        "subscribeUrl": os.environ.get("GRADWINDOW_SUBSCRIBE_URL", "").rstrip(
            "/"
        ),
        "turnstileSiteKey": os.environ.get(
            "GRADWINDOW_TURNSTILE_SITE_KEY",
            "",
        ),
        "roadmapUrl": os.environ.get("GRADWINDOW_ROADMAP_URL", "").rstrip("/"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for filename in PUBLIC_FILES:
        shutil.copy2(ROOT / filename, output_dir / filename)
    for page_name in ("index.html", "roadmap.html"):
        page_path = output_dir / page_name
        page_path.write_text(
            page_path.read_text(encoding="utf-8").replace(
                f"{DEFAULT_SITE_URL}/",
                f"{public_site_url}/",
            ).replace(
                "window.GRADWINDOW_CONFIG = {};",
                f"window.GRADWINDOW_CONFIG = {json.dumps(public_config)};",
            ),
            encoding="utf-8",
        )
    data_dir = output_dir / "data"
    data_dir.mkdir()
    for source in PUBLIC_DATA:
        shutil.copy2(source, data_dir / source.name)

    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    (output_dir / "sources.html").write_text(
        render_sources_page(), encoding="utf-8"
    )
    generated_urls = generate_index_pages(output_dir, public_site_url)
    sitemap_urls = [
        public_site_url,
        f"{public_site_url}/calendar.html",
        f"{public_site_url}/contact.html",
        f"{public_site_url}/roadmap.html",
        f"{public_site_url}/privacy.html",
        f"{public_site_url}/sources.html",
        *generated_urls,
    ]
    (output_dir / "sitemap.xml").write_text(
        render_sitemap(sitemap_urls), encoding="utf-8"
    )
    (output_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {public_site_url}/sitemap.xml\n",
        encoding="utf-8",
    )
    return output_dir / "index.html"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "other"


def generate_index_pages(output_dir: Path, public_site_url: str) -> list[str]:
    universities = read_json(UNIVERSITIES_PATH)["universities"]
    applications = read_json(APPLICATIONS_PATH)["applications"]
    predictions = read_json(PREDICTIONS_PATH)["predictions"]
    programs = read_json(PROGRAMS_PATH)["programs"]
    groups = read_json(PROGRAMME_GROUPS_PATH)["groups"]
    program_names = {item["id"]: item["name"] for item in programs}
    group_names = {item["id"]: item["name"] for item in groups}
    university_names = {item["id"]: item["school"] for item in universities}
    generated_urls: list[str] = []

    for university in universities:
        university_dir = output_dir / "university" / university["id"]
        university_dir.mkdir(parents=True, exist_ok=True)
        official = [
            item
            for item in applications
            if item["universityId"] == university["id"]
        ]
        estimated = [
            item
            for item in predictions
            if item["universityId"] == university["id"]
        ]
        canonical = f"{public_site_url}/university/{university['id']}/"
        body = (
            f"<p class=\"back\"><a href=\"../../index.html\">返回申请看板</a></p>"
            f"<p>QS {html.escape(university['rankDisplay'])} · "
            f"{html.escape(university['country'])}</p>"
            f"<p><a href=\"{html.escape(university['homepageUrl'], quote=True)}\">"
            "学校官网</a>"
            + (
                f" · <a href=\"{html.escape(university['admissionsUrl'], quote=True)}\">"
                "研究生申请入口</a>"
                if university.get("admissionsUrl")
                else ""
            )
            + "</p>"
            + render_window_list(
                official,
                "官网核验窗口",
                program_names,
                group_names,
            )
            + render_window_list(
                estimated,
                "下一周期日历平移参考",
                program_names,
                group_names,
                predicted=True,
            )
        )
        (university_dir / "index.html").write_text(
            render_static_page(
                f"{university['school']} 硕士申请时间",
                (
                    f"查看 {university['school']} 的官网核验硕士申请窗口、"
                    "截止日期与下一周期非官方日历平移参考。"
                ),
                body,
                canonical,
            ),
            encoding="utf-8",
        )
        generated_urls.append(canonical)

    by_country: dict[str, list[dict]] = {}
    for university in universities:
        by_country.setdefault(university["country"], []).append(university)
    for country, items in by_country.items():
        country_slug = slugify(country)
        country_dir = output_dir / "country" / country_slug
        country_dir.mkdir(parents=True, exist_ok=True)
        rows = "".join(
            "<li>"
            f"<strong>QS {html.escape(item['rankDisplay'])}</strong> "
            f"<a href=\"../../university/{item['id']}/\">"
            f"{html.escape(item['school'])}</a></li>"
            for item in sorted(items, key=lambda value: value["qsPosition"])
        )
        canonical = f"{public_site_url}/country/{country_slug}/"
        body = (
            '<p class="back"><a href="../../index.html">返回申请看板</a></p>'
            f"<p>共 {len(items)} 所 QS 前 200 大学。</p><ul>{rows}</ul>"
        )
        (country_dir / "index.html").write_text(
            render_static_page(
                f"{country} QS 前 200 大学硕士申请",
                f"{country} 的 QS 前 200 大学目录与硕士申请时间入口。",
                body,
                canonical,
            ),
            encoding="utf-8",
        )
        generated_urls.append(canonical)

    by_month: dict[str, list[tuple[dict, bool]]] = {}
    for item in applications:
        by_month.setdefault(item["closesAt"][:7], []).append((item, False))
    for item in predictions:
        by_month.setdefault(item["closesAt"][:7], []).append((item, True))
    for month, items in by_month.items():
        month_dir = output_dir / "deadline" / month
        month_dir.mkdir(parents=True, exist_ok=True)
        rows = "".join(
            "<li>"
            f"<strong>{html.escape(item['closesAt'])}</strong> "
            f"<a href=\"../../university/{item['universityId']}/\">"
            f"{html.escape(university_names[item['universityId']])}</a>"
            f" · {html.escape(scope_name(item, program_names, group_names))}"
            f"{' · 非官方日历平移参考' if predicted else ''}</li>"
            for item, predicted in sorted(
                items, key=lambda pair: (pair[0]["closesAt"], pair[0]["universityId"])
            )
        )
        canonical = f"{public_site_url}/deadline/{month}/"
        body = (
            '<p class="back"><a href="../../index.html">返回申请看板</a></p>'
            f"<ul>{rows}</ul>"
        )
        (month_dir / "index.html").write_text(
            render_static_page(
                f"{month} 硕士申请截止日期",
                f"汇总 {month} 的官网核验硕士申请截止日期与非官方日历平移参考。",
                body,
                canonical,
            ),
            encoding="utf-8",
        )
        generated_urls.append(canonical)
    return generated_urls


def scope_name(
    item: dict,
    program_names: dict[str, str],
    group_names: dict[str, str],
) -> str:
    if item["scopeType"] == "programme":
        return program_names.get(item["scopeId"], item["scopeId"])
    if item["scopeType"] == "programme-group":
        return group_names.get(item["scopeId"], item["scopeId"])
    return "学校级窗口"


def render_window_list(
    items: list[dict],
    heading: str,
    program_names: dict[str, str],
    group_names: dict[str, str],
    predicted: bool = False,
) -> str:
    if not items:
        return f"<section><h2>{html.escape(heading)}</h2><p>暂无记录。</p></section>"
    rows = "".join(
        "<li>"
        f"<strong>{html.escape(item['opensAt'])} 至 "
        f"{html.escape(item['closesAt'])}</strong><br>"
        f"{html.escape(scope_name(item, program_names, group_names))} · "
        f"{html.escape(item['intake'])}"
        + (
            "<br><small>同日历日期平移一年，不代表学校实际发布日期。</small>"
            if predicted
            else ""
        )
        + f"<br><a href=\"{html.escape(item['sourceUrl'], quote=True)}\">官网来源</a>"
        "</li>"
        for item in sorted(items, key=lambda value: value["closesAt"])
    )
    return f"<section><h2>{html.escape(heading)}</h2><ul>{rows}</ul></section>"


def render_static_page(
    title: str,
    description: str,
    body: str,
    canonical: str,
) -> str:
    escaped_title = html.escape(title)
    escaped_description = html.escape(description, quote=True)
    escaped_canonical = html.escape(canonical, quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title} · GradWindow</title>
  <meta name="description" content="{escaped_description}">
  <link rel="canonical" href="{escaped_canonical}">
  <meta property="og:title" content="{escaped_title} · GradWindow">
  <meta property="og:description" content="{escaped_description}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{escaped_canonical}">
  <style>
    body {{ margin: 0; background: #f7f5ef; color: #17231d; font: 16px/1.65 system-ui, sans-serif; }}
    main {{ width: min(820px, calc(100% - 32px)); margin: 48px auto; }}
    h1 {{ line-height: 1.2; }}
    h2 {{ margin-top: 36px; }}
    li {{ margin: 12px 0; }}
    a {{ color: #1e6548; }}
    small {{ color: #68736d; }}
    .back {{ margin-bottom: 28px; }}
  </style>
</head>
<body><main><h1>{escaped_title}</h1>{body}</main>{CLOUDFLARE_ANALYTICS}</body>
</html>
"""


def render_sitemap(urls: list[str]) -> str:
    entries = "".join(
        f"  <url><loc>{html.escape(url)}</loc></url>\n" for url in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}</urlset>\n"
    )


def render_sources_page() -> str:
    universities = read_json(UNIVERSITIES_PATH)["universities"]
    monitor = read_json(MONITOR_STATE_PATH, {"universities": {}})
    monitor_entries = monitor.get("universities", {})
    rows = []
    for university in sorted(universities, key=lambda item: item["qsPosition"]):
        monitor_item = monitor_entries.get(university["id"], {})
        admissions_url = university.get("admissionsUrl")
        admissions = (
            f'<a href="{html.escape(admissions_url, quote=True)}">申请入口</a>'
            if admissions_url
            else "未定位"
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(university['rankDisplay'])}</td>"
            f"<td><a href=\"{html.escape(university['homepageUrl'], quote=True)}\">"
            f"{html.escape(university['school'])}</a></td>"
            f"<td>{html.escape(university['country'])}</td>"
            f"<td>{html.escape(university['admissionsDiscovery'])}</td>"
            f"<td>{admissions}</td>"
            f"<td>{html.escape(monitor_item.get('status', 'not-checked'))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>来源与覆盖 · GradWindow</title>
  <style>
    body {{ margin: 0; background: #f7f5ef; color: #17231d; font: 14px/1.6 system-ui, sans-serif; }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 48px auto; }}
    a {{ color: #1e6548; }}
    .back {{ display: inline-block; margin-bottom: 20px; }}
    h1 {{ margin-bottom: 8px; }}
    p {{ color: #68736d; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid #d9ddd7; border-radius: 10px; background: #fffef9; }}
    table {{ width: 100%; min-width: 900px; border-collapse: collapse; }}
    th, td {{ padding: 11px 14px; border-bottom: 1px solid #e7e9e5; text-align: left; }}
    th {{ background: #f1f4ef; font-size: 11px; text-transform: uppercase; color: #68736d; }}
  </style>
</head>
<body>
  <main>
    <a class="back" href="index.html">← 返回申请雷达</a>
    <h1>来源与覆盖</h1>
    <p>完整公开 200 所大学的官网、申请入口发现状态与最近监控结果。</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>QS</th><th>大学</th><th>国家/地区</th><th>入口状态</th><th>申请页</th><th>监控</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </main>
  {CLOUDFLARE_ANALYTICS}
</body>
</html>
"""
