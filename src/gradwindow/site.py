from __future__ import annotations

import html
import shutil
from pathlib import Path

from .io import read_json
from .paths import (
    APPLICATIONS_PATH,
    APPLICATION_SOURCE_STATE_PATH,
    COVERAGE_PATH,
    MONITOR_STATE_PATH,
    PREDICTIONS_PATH,
    ROOT,
    SITE_DIR,
    PROGRAMS_PATH,
    UNIVERSITIES_PATH,
    WINDOW_POLICIES_PATH,
)

PUBLIC_FILES = ("index.html", "app.js", "styles.css")
PUBLIC_DATA = (
    UNIVERSITIES_PATH,
    APPLICATIONS_PATH,
    PREDICTIONS_PATH,
    MONITOR_STATE_PATH,
    PROGRAMS_PATH,
    WINDOW_POLICIES_PATH,
    COVERAGE_PATH,
    APPLICATION_SOURCE_STATE_PATH,
)


def build_site(output_dir: Path = SITE_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for filename in PUBLIC_FILES:
        shutil.copy2(ROOT / filename, output_dir / filename)
    data_dir = output_dir / "data"
    data_dir.mkdir()
    for source in PUBLIC_DATA:
        shutil.copy2(source, data_dir / source.name)

    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    (output_dir / "sources.html").write_text(
        render_sources_page(), encoding="utf-8"
    )
    return output_dir / "index.html"


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
</body>
</html>
"""
