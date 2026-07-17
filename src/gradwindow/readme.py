from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import quote

from .io import read_json
from .paths import (
    APPLICANT_CATEGORIES_PATH,
    APPLICATIONS_PATH,
    PREDICTIONS_PATH,
    PROGRAMME_GROUPS_PATH,
    PROGRAMS_PATH,
    ROOT,
    UNIVERSITIES_PATH,
)

SITE_URL = "https://gradwindow.com/"
REPOSITORY_URL = "https://github.com/lione12138/qs-master-applications"
README_PATH = ROOT / "README.md"
README_ZH_PATH = ROOT / "README.zh-CN.md"


def application_status(record: dict, today: date) -> str:
    opens = date.fromisoformat(record["opensAt"])
    closes = date.fromisoformat(record["closesAt"])
    if today > closes:
        return "closed"
    if today >= opens:
        return "open"
    return "upcoming" if (opens - today).days <= 30 else "future"


def generate_readmes(today: date | None = None) -> tuple[Path, Path]:
    today = today or date.today()
    universities = read_json(UNIVERSITIES_PATH)["universities"]
    applications = read_json(APPLICATIONS_PATH)["applications"]
    predictions = read_json(PREDICTIONS_PATH)["predictions"]
    programs = read_json(PROGRAMS_PATH)["programs"]
    groups = read_json(PROGRAMME_GROUPS_PATH)["groups"]
    categories = read_json(APPLICANT_CATEGORIES_PATH)["categories"]

    university_by_id = {item["id"]: item for item in universities}
    program_names = {item["id"]: item["name"] for item in programs}
    group_names = {item["id"]: item["name"] for item in groups}
    category_names = {item["id"]: item for item in categories}
    records = [{**item, "dataStatus": "official"} for item in applications] + [
        {**item, "dataStatus": "predicted"} for item in predictions
    ]
    records.sort(
        key=lambda item: (
            university_by_id[item["universityId"]]["qsPosition"],
            item["opensAt"],
        )
    )

    active = [item for item in records if application_status(item, today) == "open"]
    upcoming = [
        item for item in records if application_status(item, today) == "upcoming"
    ]
    README_PATH.write_text(
        _render_readme(
            active,
            upcoming,
            university_by_id,
            program_names,
            group_names,
            category_names,
            today,
            stats={
                "universities": len(universities),
                "programmes": len(programs),
                "official_windows": len(applications),
            },
            language="en",
        ),
        encoding="utf-8",
    )
    README_ZH_PATH.write_text(
        _render_readme(
            active,
            upcoming,
            university_by_id,
            program_names,
            group_names,
            category_names,
            today,
            stats={
                "universities": len(universities),
                "programmes": len(programs),
                "official_windows": len(applications),
            },
            language="zh",
        ),
        encoding="utf-8",
    )
    return README_PATH, README_ZH_PATH


def _scope_name(
    item: dict,
    program_names: dict[str, str],
    group_names: dict[str, str],
    language: str,
) -> str:
    if item["scopeType"] == "programme":
        return program_names.get(item["scopeId"], item["scopeId"])
    if item["scopeType"] == "programme-group":
        return group_names.get(item["scopeId"], item["scopeId"])
    return "Institution-level window" if language == "en" else "学校级窗口"


def _calendar_url(item: dict, university: dict, programme: str) -> str:
    start = item["closesAt"].replace("-", "")
    end = date.fromisoformat(item["closesAt"]).toordinal() + 1
    end_value = date.fromordinal(end).isoformat().replace("-", "")
    prefix = "[ESTIMATE] " if item["dataStatus"] == "predicted" else ""
    title = quote(f"{prefix}{university['school']} {programme} application deadline")
    return (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={title}&dates={start}%2F{end_value}"
    )


def _table(
    records: list[dict],
    university_by_id: dict[str, dict],
    program_names: dict[str, str],
    group_names: dict[str, str],
    category_names: dict[str, dict],
    language: str,
) -> str:
    if language == "en":
        header = (
            "| QS | University | Programme / scope | Applicant category | "
            "Intake | Opens | Deadline | Data | Links |\n"
            "|---:|---|---|---|---|---|---|---|---|"
        )
        empty = "_No matching windows today._"
        official = "Official"
        estimate = "Estimate"

        def links(item, calendar):
            return (
                f"[Apply]({item['applicationUrl']}) · "
                f"[Source]({item['sourceUrl']}) · [Calendar]({calendar})"
            )
    else:
        header = (
            "| QS | 大学 | 项目 / 范围 | 申请人类别 | 入学季 | 开放日期 | "
            "截止日期 | 数据类型 | 链接 |\n"
            "|---:|---|---|---|---|---|---|---|---|"
        )
        empty = "_今天没有符合条件的窗口。_"
        official = "官网核验"
        estimate = "预测参考"

        def links(item, calendar):
            return (
                f"[申请]({item['applicationUrl']}) · "
                f"[来源]({item['sourceUrl']}) · [日历]({calendar})"
            )

    if not records:
        return empty

    rows = [header]
    for item in records:
        university = university_by_id[item["universityId"]]
        programme = _scope_name(item, program_names, group_names, language).replace(
            "|", "\\|"
        )
        university_name = (
            f"{university['school']} / {university['schoolZh']}"
            if language == "zh" and university.get("schoolZh")
            else university["school"]
        )
        data_label = official if item["dataStatus"] == "official" else estimate
        categories = " / ".join(
            category_names.get(category, {}).get(
                "labelEn" if language == "en" else "labelZh",
                category,
            )
            for category in item["applicantCategories"]
        ).replace("|", "\\|")
        calendar = _calendar_url(item, university, programme)
        rows.append(
            f"| {university['rankDisplay']} | {university_name} | "
            f"{programme} | {categories} | {item['intake']} | {item['opensAt']} | "
            f"{item['closesAt']} | {data_label} | "
            f"{links(item, calendar)} |"
        )
    return "\n".join(rows)


def _render_readme(
    active: list[dict],
    upcoming: list[dict],
    university_by_id: dict[str, dict],
    program_names: dict[str, str],
    group_names: dict[str, str],
    category_names: dict[str, dict],
    today: date,
    stats: dict[str, int],
    language: str,
) -> str:
    if language == "en":
        language_link = '<a href="README.zh-CN.md">简体中文</a>'
        license_notice = (
            "[Code](LICENSE) and [data](DATA_LICENSE.md) are licensed separately. "
            "The curated dataset requires attribution and is available for "
            "noncommercial use under CC BY-NC 4.0."
        )
        tagline = (
            "Stop checking dozens of university pages. GradWindow brings exact "
            "master's application windows for QS Top 200 universities into one "
            "searchable, reviewable tracker, backed by official sources."
        )
        navigation = (
            f'{language_link} · <a href="{SITE_URL}">Live website</a> · '
            f'<a href="{REPOSITORY_URL}/issues">Issues</a>'
        )
        stats_line = (
            f"<strong>{stats['universities']:,}</strong> universities &nbsp;·&nbsp; "
            f"<strong>{stats['programmes']:,}</strong> programmes &nbsp;·&nbsp; "
            f"<strong>{stats['official_windows']:,}</strong> official windows"
        )
        primary_cta = f"[**Explore live deadlines →**]({SITE_URL})"
        features = """| | What you get |
|---|---|
| 🏛️ **Official sources first** | Every published window links back to the university page used for verification. |
| 🔎 **No hidden guesswork** | Verified dates and generated estimates are visibly separated. |
| 📅 **Ready for action** | Filter by university, programme, intake, or applicant type, then add a deadline to your calendar. |
| 🌏 **One shared university index** | QS, THE, and ARWU views use the same canonical university records. |"""
        trust_heading = "## Built for trust, not deadline spam"
        trust_copy = (
            "Admissions data is only useful when you can audit it. Parsers never "
            "publish directly: new dates enter a review queue, and an exact window "
            "is published only when its scope, intake, applicant category, opening "
            "date, closing date, and official source are known. Month-only wording "
            "stays out of the official dataset."
        )
        snapshot_heading = "## Live deadline snapshot"
        open_heading = "## Open Now"
        upcoming_heading = "## Opening Within 30 Days"
        note = (
            "> [!IMPORTANT]\n"
            "> **Estimate** means a date was shifted from the latest verified "
            "cycle. It is planning guidance, not an official forecast. Always "
            "confirm on the linked university source before applying."
        )
        updated = f"Updated **{today.isoformat()}** · {len(active):,} open now · {len(upcoming):,} opening within 30 days"
        open_summary = (
            f"<summary><strong>Open now — {len(active):,} windows</strong></summary>"
        )
        upcoming_summary = f"<summary><strong>Opening within 30 days — {len(upcoming):,} windows</strong></summary>"
        local_heading = "## Run it locally"
        local_copy = """```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
gradwindow validate
gradwindow build-site
```

See [technical documentation](docs/TECHNICAL.md) for the data model and maintenance workflows."""
        contribute_heading = "## Help make GradWindow better"
        contribute_copy = f"""Found a missing programme or a changed deadline?

- [Report a data error]({REPOSITORY_URL}/issues/new?template=report-data-error.yml)
- [Submit an official application window]({REPOSITORY_URL}/issues/new?template=submit-programme-window.yml)
- Read the [QS Top 200 coverage roadmap](docs/QS200_ROADMAP.md)

If GradWindow saves you a round of deadline hunting, **[leave a ⭐]({REPOSITORY_URL})**. It helps more applicants discover the project."""
        license_heading = "## License"
        authority_notice = "Official university pages remain the authoritative source."
    else:
        language_link = '<a href="README.md">English</a>'
        license_notice = (
            "[代码](LICENSE)与[数据](DATA_LICENSE.md)采用不同许可证。整理后的"
            "数据集须署名，并仅限 CC BY-NC 4.0 允许的非商业用途。"
        )
        tagline = (
            "不用再逐个翻找大学官网。GradWindow 把 QS 前 200 大学的硕士申请"
            "开放与截止日期整理成一个可搜索、可核验的追踪器。"
        )
        navigation = (
            f'{language_link} · <a href="{SITE_URL}">在线网站</a> · '
            f'<a href="{REPOSITORY_URL}/issues">问题反馈</a>'
        )
        stats_line = (
            f"<strong>{stats['universities']:,}</strong> 所大学 &nbsp;·&nbsp; "
            f"<strong>{stats['programmes']:,}</strong> 个项目 &nbsp;·&nbsp; "
            f"<strong>{stats['official_windows']:,}</strong> 个官网窗口"
        )
        primary_cta = f"[**查看实时申请窗口 →**]({SITE_URL})"
        features = """| | 你可以获得什么 |
|---|---|
| 🏛️ **官网来源优先** | 每条已发布窗口都链接到核验时使用的大学官网。 |
| 🔎 **不把预测伪装成事实** | 官网核验日期与生成的预测日期始终明确分开。 |
| 📅 **查完就能行动** | 按学校、项目、入学季和申请人类别筛选，并一键加入日历。 |
| 🌏 **统一的大学索引** | QS、THE 与 ARWU 排名视图共用同一份大学记录。 |"""
        trust_heading = "## 宁可少，也不要未经核验的截止日期"
        trust_copy = (
            "申请数据只有可追溯才有价值。解析器不会直接发布数据：新日期先进入"
            "审核队列；只有项目范围、入学季、申请人类别、开放日期、截止日期和"
            "官网来源全部明确后，才会进入正式数据集。“九月开放”“秋季开放”"
            "这类模糊表述不会被强行转换成具体日期。"
        )
        snapshot_heading = "## 实时申请窗口"
        open_heading = "## 正在开放"
        upcoming_heading = "## 30 天内即将开放"
        note = (
            "> [!IMPORTANT]\n"
            "> **预测参考**表示日期由最近一个官网核验周期平移得到，仅用于规划，"
            "不是学校官方预测。正式申请前请始终核对表格中的官网来源。"
        )
        updated = f"更新于 **{today.isoformat()}** · {len(active):,} 个正在开放 · {len(upcoming):,} 个将在 30 天内开放"
        open_summary = (
            f"<summary><strong>正在开放 — {len(active):,} 个窗口</strong></summary>"
        )
        upcoming_summary = f"<summary><strong>30 天内即将开放 — {len(upcoming):,} 个窗口</strong></summary>"
        local_heading = "## 本地运行"
        local_copy = """```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
gradwindow validate
gradwindow build-site
```

数据模型和维护流程见[技术文档](docs/TECHNICAL.md)。"""
        contribute_heading = "## 一起完善 GradWindow"
        contribute_copy = f"""发现遗漏的项目或变更的截止日期？

- [报告数据错误]({REPOSITORY_URL}/issues/new?template=report-data-error.yml)
- [提交官网申请窗口]({REPOSITORY_URL}/issues/new?template=submit-programme-window.yml)
- 查看 [QS 前 200 覆盖路线图](docs/QS200_ROADMAP.md)

如果 GradWindow 帮你省下了逐个查截止日期的时间，欢迎**[点一颗 ⭐]({REPOSITORY_URL})**，让更多申请人找到它。"""
        license_heading = "## 许可"
        authority_notice = "大学官网始终是权威信息来源。"

    return f"""<p align="center">
  <a href="{SITE_URL}">
    <img src="docs/readme-hero.svg" width="100%" alt="GradWindow — graduate deadlines without the guesswork">
  </a>
</p>

<p align="center">
  <a href="{SITE_URL}"><img alt="Website" src="https://img.shields.io/badge/website-gradwindow.com-1e6548?style=for-the-badge"></a>
  <a href="{REPOSITORY_URL}/actions/workflows/tests.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/lione12138/qs-master-applications/tests.yml?branch=main&amp;style=for-the-badge&amp;label=tests"></a>
  <a href="{REPOSITORY_URL}/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/lione12138/qs-master-applications?style=for-the-badge&amp;color=f3b72e"></a>
  <a href="LICENSE"><img alt="Code license" src="https://img.shields.io/badge/code-AGPL--3.0-315f4c?style=for-the-badge"></a>
</p>

<p align="center">{navigation}</p>

<p align="center">{stats_line}</p>

{tagline}

{primary_cta}

{features}

{trust_heading}

{trust_copy}

{snapshot_heading}

{note}

{updated}

<details>
{open_summary}

{open_heading}

{_table(active, university_by_id, program_names, group_names, category_names, language)}

</details>

<details>
{upcoming_summary}

{upcoming_heading}

{_table(upcoming, university_by_id, program_names, group_names, category_names, language)}

</details>

{local_heading}

{local_copy}

{contribute_heading}

{contribute_copy}

{license_heading}

{license_notice} {authority_notice}
"""
