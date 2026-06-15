from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import quote

from .io import read_json
from .paths import (
    APPLICANT_CATEGORIES_PATH,
    APPLICATIONS_PATH,
    PREDICTIONS_PATH,
    PROGRAMS_PATH,
    PROGRAMME_GROUPS_PATH,
    ROOT,
    UNIVERSITIES_PATH,
)

SITE_URL = "https://lione12138.github.io/qs-master-applications/"
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
    records = [
        {**item, "dataStatus": "official"} for item in applications
    ] + [{**item, "dataStatus": "predicted"} for item in predictions]
    records.sort(
        key=lambda item: (
            university_by_id[item["universityId"]]["qsPosition"],
            item["opensAt"],
        )
    )

    active = [
        item for item in records if application_status(item, today) == "open"
    ]
    upcoming = [
        item
        for item in records
        if application_status(item, today) == "upcoming"
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
    title = quote(
        f"{prefix}{university['school']} {programme} application deadline"
    )
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
        links = lambda item, calendar: (
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
        links = lambda item, calendar: (
            f"[申请]({item['applicationUrl']}) · "
            f"[来源]({item['sourceUrl']}) · [日历]({calendar})"
        )
    if not records:
        return empty

    rows = [header]
    for item in records:
        university = university_by_id[item["universityId"]]
        programme = _scope_name(
            item, program_names, group_names, language
        ).replace("|", "\\|")
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
    language: str,
) -> str:
    if language == "en":
        language_link = "[中文](README.zh-CN.md)"
        intro = (
            "A QS Top 200 master's application tracker using official "
            "university sources. The tables below show only applications "
            "that are open now or scheduled to open within 30 days."
        )
        open_heading = "## Open Now"
        upcoming_heading = "## Opening Within 30 Days"
        note = (
            "> **Estimate** means the date is shifted from the latest "
            "verified cycle and is not an official forecast. Always confirm "
            "dates on the linked university source."
        )
        updated = f"Status date: **{today.isoformat()}**"
    else:
        language_link = "[English](README.md)"
        intro = (
            "基于大学官网数据的 QS 前 200 硕士申请追踪项目。下面只展示"
            "当前正在开放，以及未来 30 天内即将开放的申请窗口。"
        )
        open_heading = "## 正在开放"
        upcoming_heading = "## 30 天内即将开放"
        note = (
            "> **预测参考**表示日期由最近一个官网核验周期平移一年得到，"
            "不是学校官方预测。申请前请始终核对表格中的官网来源。"
        )
        updated = f"状态日期：**{today.isoformat()}**"

    return f"""# GradWindow

[![Tests](https://github.com/lione12138/qs-master-applications/actions/workflows/tests.yml/badge.svg)](https://github.com/lione12138/qs-master-applications/actions/workflows/tests.yml)
[![Website](https://img.shields.io/badge/Website-GradWindow-1e6548)]({SITE_URL})

{language_link} · [Live website]({SITE_URL})

{intro}

{updated}

{note}

{open_heading}

{_table(active, university_by_id, program_names, group_names, category_names, language)}

{upcoming_heading}

{_table(upcoming, university_by_id, program_names, group_names, category_names, language)}
"""
