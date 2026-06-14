# GradWindow

[![Tests](https://github.com/lione12138/qs-master-applications/actions/workflows/tests.yml/badge.svg)](https://github.com/lione12138/qs-master-applications/actions/workflows/tests.yml)
[![GitHub Pages](https://github.com/lione12138/qs-master-applications/actions/workflows/pages.yml/badge.svg)](https://lione12138.github.io/qs-master-applications/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

QS 2026 前 200 所大学硕士申请追踪站。项目参考
[Research Seasonal School Radar](https://github.com/lione12138/research-school-radar)
的透明数据流水线、可信分层和静态发布结构。

[技术架构](docs/TECHNICAL.md) | [贡献指南](CONTRIBUTING.md)
| [QS 前30 分批路线图](docs/TOP30_ROADMAP.md)

## 当前正式数据

- `data/universities.json`
  - QS World University Rankings 2026 前 200 所学校
  - 200 个官方主页
  - ROR 机构标识与官方域名
  - 研究生申请入口及发现状态
- `data/applications.json`
  - 保存经过官网核验的学校级、项目组级或项目级窗口
  - 每条记录明确作用范围、入学季和申请人类别，不包含推测日期
  - `intakeDetails` 同时保存周期年份、学期和起始月份，`intake` 只负责展示
- `data/predictions.json`
  - 基于同一范围最近一个官网核验周期生成下一周期参考日期
  - 预测与正式数据分开存储、分开统计，并始终标注为非官方
  - 新周期官网日期发布后，对应周期预测会被正式记录自动替代
  - 只有一个历史周期时标为低置信度；连续周期完全重复后才提高置信度
- `data/programs.json`
  - 项目目录；项目可以继承上级窗口，只记录自身例外
- `data/programme-groups.json`
  - 显式项目组字典；项目组窗口和项目继承关系都必须引用存在且属于同校的 ID
- `data/applicant-categories.json`
  - 申请人类别字典；禁止在窗口记录中临时创造近义类别
- `data/window-policies.json`
  - 官网核验过的日期粒度规则，例如项目独立、院系共享轮次或学校共享窗口
- `data/ops/monitor-state.json`
  - 200 所学校官网的每日可访问性和内容指纹
  - 同一页面变化需连续出现两次，只触发复核，不会直接覆盖截止日期
- `data/ops/application-source-state.json`
  - 单独监控已经发布的精确日期来源页
  - 多条窗口引用同一官网时每天只请求一次
- `data/evidence/`
  - 保存正文哈希、短证据摘录、匹配文本前后文、正文选择器和抓取元数据
  - 不保存整页 HTML，也不会发布到静态网站
- `data/ops/review-queue.json` 与 `data/ops/reports/`
  - 内部审核队列和每日监控报告，不发布到静态网站
- `data/coverage.json`
  - 从正式数据自动生成的 QS 前30入口、规则、项目和精确日期覆盖率
- `data/ops/window-candidates.json`
  - 待人工审核的精确窗口候选，不发布到静态网站
  - 自动解析器只能写入这里，不能直接修改正式日期

## 学校的申请期是不是基本一样

你的直觉在不少学校是对的：同一学校通常有共同的申请季，部分院系还会让
多个授课型硕士共用一组轮次。真正容易不同的通常是截止日、是否滚动录取、
奖学金节点和少数项目例外，而不是每个项目都有完全独立的开放期。

官网规则也并不统一：

- Cambridge 和 Stanford 明确要求按具体项目确认截止日
- Imperial 同时存在院系共享轮次、招满即止和项目例外
- ETH Zurich 的多数硕士共享申请窗口，但按前置学历来源等申请人类别分流

因此本站采用继承模型：`学校默认窗口 -> 项目组窗口 -> 项目例外`。下级只有
在官网明确给出不同日期时才覆盖上级规则。这既避免维护 200 所学校全部项目
的重复数据，也不会把一个统一日期错误套到例外项目上。

## 数据来源

- 排名版本：QS World University Rankings 2026
- QS 官方页面：<https://www.topuniversities.com/world-university-rankings>
- 官方发布日期：2025-06-19
- 排名表解析源：
  <https://github.com/olgagaffarova/QS-University-Rankings-2026>
- 学校官方域名：ROR v2 API <https://ror.readme.io/>
- 申请页：仅使用匹配后学校官方域名上的页面

前 200 的选择规则是排名表中的前 200 条机构记录。并列名次保留 QS 原始
名次，因此第 200 条记录的名次可能小于 200。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
gradwindow build-site
python -m http.server 8000 --directory site
```

访问 `http://localhost:8000`。

前端状态规则：开放日距离用户当天 1–30 天的正式窗口归为“即将开放”；
31 天及以后归为“未来开放”；开放日当天开始归为“正在开放”。

## 数据任务

统一 CLI：

```powershell
gradwindow validate
gradwindow monitor
gradwindow monitor-sources
gradwindow update-deadlines --dry-run
gradwindow predictions
gradwindow migrate-intakes
gradwindow export-schemas
gradwindow coverage
gradwindow approve-window candidate-id --reviewer maintainer-name
gradwindow build-site
gradwindow pipeline
```

旧的 `scripts/test_data.py`、`scripts/monitor_universities.py` 和
`scripts/update_data.py` 仍作为兼容入口保留。

## 项目结构

```text
data/                 正式数据、窗口策略、人工覆盖与审核状态
data/ops/             高频运行状态、候选、审核队列和日报
src/gradwindow/       可安装的数据流水线与 CLI
scripts/              排名导入、入口发现及兼容入口
tests/                离线数据契约和行为测试
docs/                 技术说明
site/                 构建生成的 GitHub Pages 发布目录
```

`data/admissions-overrides.json` 保存人工核验入口，优先级高于自动发现结果。
`data/coverage.json` 是生成结果，不应手工修改。

日期记录必须明确作用范围。`scopeType` 可为 `institution`、
`programme-group` 或 `programme`：

```json
{
  "id": "university-program-intake-round",
  "universityId": "university-id",
  "scopeType": "programme",
  "scopeId": "msc-example",
  "intake": "2027 Fall",
  "intakeDetails": {
    "label": "2027 Fall",
    "cycleYear": 2027,
    "academicYearEnd": null,
    "term": "fall",
    "startMonth": 9
  },
  "round": "Round 1",
  "applicantCategories": ["international-bachelors"],
  "opensAt": "2026-09-01",
  "closesAt": "2026-12-01",
  "applicationUrl": "https://official.example/apply",
  "sourceUrl": "https://official.example/deadlines",
  "verifiedAt": "2026-06-13",
  "evidence": "The official page states that international applicants..."
}
```

核心数据由 Pydantic v2 校验，并在 `docs/schemas/` 导出对应 JSON Schema。
抓取统一使用 `httpx + tenacity`，包含重定向、超时、按域名限速、可重试
错误分类和指数退避。

## GitHub Actions

- `tests.yml`：推送、PR 和手动触发时在 Python 3.10、3.12 上测试，并只构建一次站点制品
- `pages.yml`：只下载已通过测试的 `site` 制品并部署 GitHub Pages
- `update-data.yml`：UTC 04:17 运行监控、候选生成、预测和校验，然后更新审核 PR
  - 同一内容变化连续出现两次后进入审核队列
  - 只有截止日期关键词变化才创建去重 Issue；普通页面变化只进入报告
  - bot 不再直接推送 `main`，审核分支会单独触发测试

静态构建同时生成 `/university/`、`/country/`、`/deadline/` 页面以及
`sitemap.xml`、`robots.txt` 和 OpenGraph 元数据，便于搜索和外部引用。

公共仓库的标准 GitHub-hosted Actions 通常不计费；私有仓库受 GitHub
账户包含额度和届时计费规则限制。

## 当前 Top 30 进度

截至 2026-06-14：

- 官方研究生入口：28/30
- 人工核验入口：25/30
- 日期粒度规则：15/30
- 有代表项目的学校：8/30
- 有精确日期的学校：6/30
- 正式日期窗口：9
- 下一周期预测窗口：9

前三批 QS 1–15 的规则已经核验完成。Stanford、Oxford、Harvard 和 MIT
公布了 2027 周期的大致开放时间，但尚未给出足以写入日历的精确日期，因此
只作为周期预告展示。Cambridge、ETH Zurich、UCL、NTU、Peking
University 和 Penn 已有官网精确窗口。
