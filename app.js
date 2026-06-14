const state = {
  data: [],
  universities: [],
  programs: [],
  programmeGroups: [],
  applicantCategoryLabels: {},
  policies: [],
  coverage: null,
  sourceMonitor: {},
  officialCount: 0,
  predictionCount: 0,
  meta: {},
  search: "",
  region: "all",
  intake: "all",
  status: "all",
  favorites: new Set(),
  favoritesOnly: false,
  top30Only: false,
};

const STATUS_LABELS = {
  open: {
    title: "正在开放",
    description: "当前可以提交申请",
  },
  upcoming: {
    title: "即将开放",
    description: "开放日期尚未到来",
  },
  predicted: {
    title: "下一周期预测",
    description: "按上一周期同一日历日期平移一年，不代表学校真实预测",
  },
  closed: {
    title: "当前已截止",
    description: "本轮申请已结束",
  },
  unknown: {
    title: "学校与项目目录",
    description: "查看全部学校入口、日期规则与当前覆盖情况",
  },
};

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

const shortDateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  timeZone: "UTC",
});

function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

function safeUrl(value) {
  try {
    const url = new URL(value, window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function makeElement(tag, options = {}) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.title) node.title = options.title;
  return node;
}

function makeCell(label, ...children) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  children.filter(Boolean).forEach((child) => cell.appendChild(child));
  return cell;
}

function makeLink(text, url, className = "") {
  const validUrl = safeUrl(url);
  if (!validUrl) return makeElement("span", { className, text });
  const link = makeElement("a", { className, text });
  link.href = validUrl;
  link.target = "_blank";
  link.rel = "noreferrer";
  return link;
}

function makeTextStack(primary, secondary, primaryClass = "date-primary") {
  const wrapper = document.createDocumentFragment();
  wrapper.appendChild(makeElement("span", { className: primaryClass, text: primary }));
  if (secondary) {
    wrapper.appendChild(
      makeElement("span", { className: "date-secondary", text: secondary }),
    );
  }
  return wrapper;
}

function favoriteKey(type, id) {
  return `${type}:${id}`;
}

function saveFavorites() {
  localStorage.setItem("gradwindow:favorites", JSON.stringify([...state.favorites]));
  updateFavoriteControls();
}

function toggleFavorite(key) {
  if (state.favorites.has(key)) state.favorites.delete(key);
  else state.favorites.add(key);
  saveFavorites();
  render();
}

function makeFavoriteButton(key) {
  const active = state.favorites.has(key);
  const button = makeElement("button", {
    className: `icon-button favorite-button${active ? " active" : ""}`,
    text: active ? "已收藏" : "收藏",
    title: active ? "取消收藏" : "收藏",
  });
  button.type = "button";
  button.setAttribute("aria-pressed", String(active));
  button.addEventListener("click", () => toggleFavorite(key));
  return button;
}

function todayUtc() {
  const now = new Date();
  return new Date(
    Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()),
  );
}

function getStatus(record, today = todayUtc()) {
  if (record.dataStatus === "predicted") return "predicted";
  if (!record.opensAt || !record.closesAt) return "unknown";
  const opens = parseDate(record.opensAt);
  const closes = parseDate(record.closesAt);
  if (today < opens) return "upcoming";
  if (today > closes) return "closed";
  return "open";
}

function daysUntil(dateValue) {
  return Math.ceil((parseDate(dateValue) - todayUtc()) / 86_400_000);
}

function formatDate(value) {
  return dateFormatter.format(parseDate(value));
}

function deadlineNote(record, status) {
  if (status === "predicted") {
    return `同日历日期平移 · 参考 ${record.sourceCycle}`;
  }
  const days = daysUntil(record.closesAt);
  if (status === "closed") return `${Math.abs(days)} 天前截止`;
  if (days === 0) return "今天截止";
  if (days === 1) return "明天截止";
  if (days > 1 && days <= 30) return `${days} 天后截止`;
  return record.intake;
}

const APPLICANT_CATEGORY_LABELS = {
  all: "所有申请人",
  "international-bachelors": "境外本科申请人",
  esop: "ESOP 奖学金申请人",
  "direct-doctorate": "直博申请人",
  "swiss-bachelors": "瑞士高校本科申请人",
  "requires-uk-study-visa": "需要英国学生签证",
  "does-not-require-uk-study-visa": "无需英国学生签证",
};

function applicantCategoryText(categories = []) {
  return categories
    .map(
      (category) =>
        state.applicantCategoryLabels[category] ||
        APPLICANT_CATEGORY_LABELS[category] ||
        category,
    )
    .join("、");
}

function sourceMonitorDescription(record) {
  const monitor = record.sourceMonitor || {};
  if (monitor.changed) return ["来源页面有变化", "candidate"];
  if (monitor.status === "ok") return ["来源检查正常", "verified"];
  if (monitor.status === "blocked") return ["来源限制访问", "candidate"];
  if (monitor.status === "error" || monitor.status === "http-error") {
    return ["来源检查异常", "homepage"];
  }
  return ["来源尚未检查", "homepage"];
}

function googleCalendarUrl(record) {
  const start = record.closesAt.replaceAll("-", "");
  const endDate = parseDate(record.closesAt);
  endDate.setUTCDate(endDate.getUTCDate() + 1);
  const end = endDate.toISOString().slice(0, 10).replaceAll("-", "");
  const prefix = record.dataStatus === "predicted" ? "[预测] " : "";
  const title = `${prefix}${record.school} ${record.program} 申请截止`;
  const details = [
    record.dataStatus === "predicted"
      ? "非官方日历平移参考，不代表学校真实预测；请在提交前核对官网。"
      : "",
    `申请入口：${record.applicationUrl}`,
    `信息来源：${record.sourceUrl}`,
  ].filter(Boolean).join("\n");
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates: `${start}/${end}`,
    details,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function downloadIcs(record) {
  const start = record.closesAt.replaceAll("-", "");
  const endDate = parseDate(record.closesAt);
  endDate.setUTCDate(endDate.getUTCDate() + 1);
  const end = endDate.toISOString().slice(0, 10).replaceAll("-", "");
  const escapeIcs = (value) =>
    value
      .replaceAll("\\", "\\\\")
      .replaceAll("\n", "\\n")
      .replaceAll(",", "\\,")
      .replaceAll(";", "\\;");
  const body = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//GradWindow//Application Deadline//CN",
    "BEGIN:VEVENT",
    `UID:${record.id}@gradwindow`,
    `DTSTAMP:${new Date().toISOString().replaceAll(/[-:]/g, "").split(".")[0]}Z`,
    `DTSTART;VALUE=DATE:${start}`,
    `DTEND;VALUE=DATE:${end}`,
    `SUMMARY:${escapeIcs(`${record.dataStatus === "predicted" ? "[预测] " : ""}${record.school} ${record.program} 申请截止`)}`,
    `DESCRIPTION:${escapeIcs(`${record.dataStatus === "predicted" ? "非官方日历平移参考，不代表学校真实预测；请在提交前核对官网。\n" : ""}申请入口：${record.applicationUrl}\n信息来源：${record.sourceUrl}`)}`,
    `URL:${record.applicationUrl}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");

  const blob = new Blob([body], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${record.id}-deadline.ics`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function downloadFavoriteCalendars() {
  const records = state.data.filter((record) =>
    state.favorites.has(favoriteKey("window", record.id)),
  );
  if (!records.length) return;
  const events = records.flatMap((record) => {
    const start = record.closesAt.replaceAll("-", "");
    const endDate = parseDate(record.closesAt);
    endDate.setUTCDate(endDate.getUTCDate() + 1);
    const end = endDate.toISOString().slice(0, 10).replaceAll("-", "");
    return [
      "BEGIN:VEVENT",
      `UID:${record.id}@gradwindow`,
      `DTSTART;VALUE=DATE:${start}`,
      `DTEND;VALUE=DATE:${end}`,
      `SUMMARY:${record.dataStatus === "predicted" ? "[ESTIMATE] " : ""}${record.school} ${record.program} application deadline`,
      `URL:${record.applicationUrl}`,
      "END:VEVENT",
    ];
  });
  const body = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//GradWindow//Favorite Deadlines//CN",
    ...events,
    "END:VCALENDAR",
  ].join("\r\n");
  const blob = new Blob([body], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "gradwindow-favorite-deadlines.ics";
  anchor.click();
  URL.revokeObjectURL(url);
}

function uniqueSorted(values) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function populateSelect(elementId, values) {
  const select = document.getElementById(elementId);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function filteredRecords() {
  const query = state.search.trim().toLocaleLowerCase("zh-CN");
  return state.data.filter((record) => {
    const searchable = [
      record.school,
      record.schoolZh,
      record.program,
      record.country,
      record.region,
    ]
      .join(" ")
      .toLocaleLowerCase("zh-CN");

    return (
      (!query || searchable.includes(query)) &&
      (state.region === "all" || record.region === state.region) &&
      (state.intake === "all" || record.intake === state.intake) &&
      (!state.top30Only || record.qsRank <= 30) &&
      (!state.favoritesOnly ||
        state.favorites.has(favoriteKey("window", record.id)))
    );
  });
}

function filteredUniversities() {
  const query = state.search.trim().toLocaleLowerCase("zh-CN");
  if (state.intake !== "all") return [];
  return state.universities.filter((university) => {
    const searchable = [
      university.school,
      university.schoolZh,
      university.country,
      university.region,
    ]
      .join(" ")
      .toLocaleLowerCase("zh-CN");
    return (
      (!query || searchable.includes(query)) &&
      (state.region === "all" || university.region === state.region) &&
      (!state.top30Only || university.qsPosition <= 30) &&
      (!state.favoritesOnly ||
        state.favorites.has(favoriteKey("university", university.id)))
    );
  });
}

function createRow(record, status) {
  const row = document.createElement("tr");
  const days = daysUntil(record.closesAt);
  const deadlineClass =
    status === "open" && days >= 0 && days <= 14 ? "deadline-soon" : "";

  const rank = makeElement("span", { className: "rank-cell", text: `#${record.qsRank}` });
  const school = document.createDocumentFragment();
  school.appendChild(
    makeLink(record.school, record.applicationUrl, "school-link"),
  );
  school.appendChild(
    makeElement("span", {
      className: "school-meta",
      text: [record.schoolZh, record.country].filter(Boolean).join(" · "),
    }),
  );
  const programme = makeTextStack(
    record.program,
    `${record.intake}${record.round ? ` · ${record.round}` : ""}`,
  );
  const source = document.createDocumentFragment();
  const predicted = record.dataStatus === "predicted";
  const [sourceStatus, sourceClass] = predicted
    ? ["基于上周期预测", "predicted"]
    : sourceMonitorDescription(record);
  source.append(
    makeLink(
      predicted ? "查看参考周期官网 ↗" : "查看官网 ↗",
      record.sourceUrl,
      "source-link",
    ),
    makeElement("span", {
      className: `source-badge ${sourceClass}`,
      text: sourceStatus,
    }),
    makeElement("span", {
      className: "date-secondary",
      text: predicted
        ? `参考 ${record.sourceCycle} · ${predictionConfidenceText(record)}`
        : `核验于 ${record.verifiedAt}`,
    }),
  );
  const deadline = makeTextStack(
    formatDate(record.closesAt),
    deadlineNote(record, status),
    `date-primary ${deadlineClass}`.trim(),
  );
  const calendar = makeElement("div", { className: "calendar-actions" });
  calendar.appendChild(
    makeLink("G", googleCalendarUrl(record), "icon-button"),
  );
  const ics = makeElement("button", {
    className: "icon-button",
    text: "ICS",
    title: "下载 ICS 日历文件",
  });
  ics.type = "button";
  ics.addEventListener("click", () => downloadIcs(record));
  calendar.appendChild(ics);
  calendar.appendChild(makeFavoriteButton(favoriteKey("window", record.id)));

  row.append(
    makeCell("QS 排名", rank),
    makeCell("大学", school),
    makeCell("项目", programme),
    makeCell(
      "适用人群",
      makeElement("span", {
        className: "applicant-category",
        text: applicantCategoryText(record.applicantCategories),
      }),
    ),
    makeCell(
      "开放日期",
      makeTextStack(
        formatDate(record.opensAt),
        predicted ? "预计开放 · 非官方" : "开放申请",
      ),
    ),
    makeCell("截止日期", deadline),
    makeCell("日历", calendar),
    makeCell("来源", source),
  );
  return row;
}

function predictionConfidenceText(record) {
  const labels = { low: "低置信度", medium: "中置信度", high: "高置信度" };
  return `${labels[record.confidence] || "预测"} · ${record.evidenceCycleCount} 个历史周期`;
}

function createGroup(status, records) {
  const heading = STATUS_LABELS[status];
  const { section, tbody } = createTableSection(
    status,
    heading,
    `${records.length} 个窗口`,
    [
      "QS 排名",
      "大学 / 申请入口",
      "项目 / 入学季",
      "适用人群",
      "开放日期",
      "截止日期",
      "添加日历",
      "数据来源",
    ],
  );
  records.forEach((record) => tbody.appendChild(createRow(record, status)));
  return section;
}

function createTableSection(status, heading, countLabel, columns, tableClass = "") {
  const section = makeElement("section", { className: "application-group" });
  section.dataset.status = status;

  const groupHeading = makeElement("div", { className: "group-heading" });
  const title = makeElement("h3");
  title.append(
    makeElement("span", { className: `status-indicator ${status}` }),
    document.createTextNode(heading.title),
  );
  groupHeading.append(
    title,
    makeElement("p", { text: `${heading.description} · ${countLabel}` }),
  );

  const wrapper = makeElement("div", { className: "table-wrap" });
  const table = makeElement("table", {
    className: `application-table ${tableClass}`.trim(),
  });
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  columns.forEach((column) =>
    headRow.appendChild(makeElement("th", { text: column })),
  );
  head.appendChild(headRow);
  const tbody = document.createElement("tbody");
  table.append(head, tbody);
  wrapper.appendChild(table);
  section.append(groupHeading, wrapper);
  return { section, tbody };
}

function directoryStatus(university) {
  const status = university.admissionsDiscovery;
  if (status === "curated") return ["人工核验入口", "verified"];
  if (status === "discovered") return ["官网自动定位", "discovered"];
  if (status === "low-confidence") return ["候选页待复核", "candidate"];
  return ["官方主页已接入", "homepage"];
}

function monitorStatus(university) {
  const monitor = university.monitor || {};
  if (monitor.changed) return ["页面有变化", "candidate"];
  if (monitor.status === "ok") return ["检查正常", "verified"];
  if (monitor.status === "blocked") return ["限制自动访问", "candidate"];
  if (monitor.status === "error" || monitor.status === "http-error") {
    return ["检查异常", "homepage"];
  }
  return ["尚未检查", "homepage"];
}

function policyDescription(university) {
  const policy = university.windowPolicy;
  if (!policy) return ["待核验窗口粒度", "打开具体项目后确认"];
  const guidance = policy.cycleGuidance?.opensText;
  const windowCount = university.coverage?.windowCount || 0;
  const prefix = windowCount ? `已发布 ${windowCount} 条 · ` : "";
  if (policy.model === "programme-specific") {
    return [
      "项目级截止日",
      `${prefix}${guidance ? `下一周期：${guidance}` : "同校不同项目可能不同"}`,
    ];
  }
  if (policy.model === "mixed") {
    return [
      "学院轮次 + 项目例外",
      `${prefix}${guidance ? `下一周期：${guidance}` : "部分课程招满即止"}`,
    ];
  }
  if (policy.model === "applicant-category") {
    return [
      "学校级共享窗口",
      `${prefix}${guidance ? `下一周期：${guidance}` : "按申请人类别分流"}`,
    ];
  }
  return ["继承默认申请周期", "项目可覆盖例外日期"];
}

function mastersAvailabilityDescription(university) {
  const availability = university.windowPolicy?.mastersAvailability;
  if (availability === "broad") return ["广泛招收硕士", "可选择代表项目"];
  if (availability === "limited") {
    return ["硕士招生有限", "部分方向不直接招收"];
  }
  return ["尚未核验", "需检查具体培养方向"];
}

function renderCoverage() {
  if (!state.coverage) return;
  const summary = state.coverage.summary;
  const target = summary.targetUniversities;
  document.getElementById("coverage-entries").textContent =
    `${summary.entriesLocated}/${target}`;
  document.getElementById("coverage-policies").textContent =
    `${summary.policiesVerified}/${target}`;
  document.getElementById("coverage-programs").textContent =
    `${summary.universitiesWithPrograms}/${target}`;
  document.getElementById("coverage-windows").textContent =
    `${summary.universitiesWithWindows}/${target}`;
  document.getElementById("coverage-records").textContent =
    summary.verifiedWindows;
  document.getElementById("coverage-predictions").textContent =
    summary.predictedWindows;

  const batches = document.getElementById("coverage-batches");
  batches.replaceChildren();
  state.coverage.batches.forEach((batch) => {
    const complete = batch.policiesVerified === batch.universities;
    const card = makeElement("div", {
      className: `coverage-batch${complete ? " complete" : ""}`,
    });
    card.append(
      makeElement("strong", {
        text: `第 ${batch.batch} 批 · QS ${batch.positions[0]}–${batch.positions[1]}`,
      }),
      document.createTextNode(
        `规则 ${batch.policiesVerified}/${batch.universities} · 项目 ${batch.universitiesWithPrograms}/${batch.universities} · 正式日期 ${batch.universitiesWithWindows}/${batch.universities} · 预测 ${batch.predictedWindows}`,
      ),
    );
    batches.appendChild(card);
  });
  document.getElementById("coverage-panel").hidden = false;
}

function createUniversityGroup(universities) {
  const heading = STATUS_LABELS.unknown;
  const { section, tbody } = createTableSection(
    "unknown",
    heading,
    `${universities.length} 所大学`,
    [
      "QS 排名",
      "大学",
      "国家/地区",
      "硕士范围",
      "入口状态",
      "最近监控",
      "研究生申请",
      "学校官网",
      "日期说明",
    ],
    "university-table",
  );
  universities
    .sort((a, b) => a.qsPosition - b.qsPosition)
    .forEach((university) => {
      const [statusLabel, statusClass] = directoryStatus(university);
      const [monitorLabel, monitorClass] = monitorStatus(university);
      const rankLabel = university.rankDisplay.startsWith("=")
        ? university.rankDisplay
        : `#${university.rankDisplay}`;
      const directUrl = university.admissionsUrl;
      const directLabel =
        university.admissionsDiscovery === "low-confidence"
          ? "打开候选页"
          : "打开申请入口";
      const row = document.createElement("tr");
      const school = makeTextStack(university.school, university.schoolZh);
      const admissions = directUrl
        ? makeLink(directLabel, directUrl, "school-link")
        : makeElement("span", {
            className: "school-meta",
            text: "需从项目目录进入",
          });
      const actions = document.createDocumentFragment();
      actions.appendChild(admissions);
      actions.appendChild(
        makeFavoriteButton(favoriteKey("university", university.id)),
      );
      const [policyPrimary, policySecondary] = policyDescription(university);
      const [mastersPrimary, mastersSecondary] =
        mastersAvailabilityDescription(university);
      row.append(
        makeCell("QS 排名", makeElement("span", { className: "rank-cell", text: rankLabel })),
        makeCell("大学", school),
        makeCell("国家/地区", makeElement("span", { text: university.country })),
        makeCell("硕士范围", makeTextStack(mastersPrimary, mastersSecondary)),
        makeCell("入口状态", makeElement("span", { className: `source-badge ${statusClass}`, text: statusLabel })),
        makeCell("最近监控", makeElement("span", { className: `source-badge ${monitorClass}`, text: monitorLabel })),
        makeCell("研究生申请", actions),
        makeCell("学校官网", makeLink("官方网站 ↗", university.homepageUrl, "source-link")),
        makeCell("日期说明", makeTextStack(policyPrimary, policySecondary)),
      );
      tbody.appendChild(row);
    });
  return section;
}

function renderCounts(records, universities) {
  const counts = {
    all: records.length + universities.length,
    open: 0,
    upcoming: 0,
    predicted: 0,
    closed: 0,
    unknown: universities.length,
  };
  records.forEach((record) => {
    counts[getStatus(record)] += 1;
  });
  Object.entries(counts).forEach(([status, count]) => {
    document.getElementById(`count-${status}`).textContent = count;
  });
  return counts;
}

function render() {
  const baseRecords = filteredRecords();
  const baseUniversities = filteredUniversities();
  const counts = renderCounts(baseRecords, baseUniversities);
  const records =
    state.status === "all"
      ? baseRecords
      : baseRecords.filter((record) => getStatus(record) === state.status);
  const container = document.getElementById("application-groups");
  const emptyState = document.getElementById("empty-state");
  container.replaceChildren();

  ["open", "upcoming", "predicted", "closed"].forEach((status) => {
    if (state.status !== "all" && state.status !== status) return;
    const groupRecords = records
      .filter((record) => getStatus(record) === status)
      .sort((a, b) => a.qsRank - b.qsRank || a.closesAt.localeCompare(b.closesAt));
    if (groupRecords.length) {
      container.appendChild(createGroup(status, groupRecords));
    }
  });
  if (
    (state.status === "all" || state.status === "unknown") &&
    baseUniversities.length
  ) {
    container.appendChild(createUniversityGroup([...baseUniversities]));
  }

  emptyState.hidden =
    records.length > 0 ||
    ((state.status === "all" || state.status === "unknown") &&
      baseUniversities.length > 0);
  document.getElementById("hero-open-count").textContent = counts.open;
  updateFavoriteControls();
}

function syncUrl() {
  const params = new URLSearchParams();
  if (state.search) params.set("q", state.search);
  if (state.region !== "all") params.set("region", state.region);
  if (state.intake !== "all") params.set("intake", state.intake);
  if (state.status !== "all") params.set("status", state.status);
  if (state.top30Only) params.set("top", "30");
  history.replaceState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}${location.hash}`);
}

function loadUrlState() {
  const params = new URLSearchParams(location.search);
  state.search = params.get("q") || "";
  state.region = params.get("region") || "all";
  state.intake = params.get("intake") || "all";
  state.status = params.get("status") || "all";
  state.top30Only = params.get("top") === "30";
}

function updateFavoriteControls() {
  const count = state.favorites.size;
  document.getElementById("favorite-count").textContent = count;
  document
    .getElementById("favorites-toggle")
    .classList.toggle("active", state.favoritesOnly);
  document
    .getElementById("top30-toggle")
    .classList.toggle("active", state.top30Only);
  document.getElementById("export-favorites").disabled = !state.data.some(
    (record) => state.favorites.has(favoriteKey("window", record.id)),
  );
}

function setupHero() {
  const futureDeadline = state.data
    .filter(
      (record) =>
        record.dataStatus === "official" && getStatus(record) !== "closed",
    )
    .sort((a, b) => a.closesAt.localeCompare(b.closesAt))[0];
  if (!futureDeadline) {
    document.getElementById("hero-deadline-day").textContent = "200";
    document.getElementById("hero-deadline-month").textContent = "SCHOOLS";
    document.getElementById("hero-deadline-school").textContent =
      "Official admissions directory";
    return;
  }
  const parts = shortDateFormatter
    .formatToParts(parseDate(futureDeadline.closesAt))
    .reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
  document.getElementById("hero-deadline-day").textContent = parts.day;
  document.getElementById("hero-deadline-month").textContent =
    parts.month.toUpperCase();
  document.getElementById("hero-deadline-school").textContent =
    futureDeadline.school;
}

function bindEvents() {
  document.getElementById("search-input").addEventListener("input", (event) => {
    state.search = event.target.value;
    syncUrl();
    render();
  });
  document.getElementById("region-filter").addEventListener("change", (event) => {
    state.region = event.target.value;
    syncUrl();
    render();
  });
  document.getElementById("intake-filter").addEventListener("change", (event) => {
    state.intake = event.target.value;
    syncUrl();
    render();
  });
  document.querySelectorAll(".status-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.status = button.dataset.status;
      syncUrl();
      document
        .querySelectorAll(".status-tab")
        .forEach((tab) => tab.classList.toggle("active", tab === button));
      render();
    });
  });
  document.getElementById("favorites-toggle").addEventListener("click", () => {
    state.favoritesOnly = !state.favoritesOnly;
    render();
  });
  document.getElementById("top30-toggle").addEventListener("click", () => {
    state.top30Only = !state.top30Only;
    syncUrl();
    render();
  });
  document
    .getElementById("export-favorites")
    .addEventListener("click", downloadFavoriteCalendars);
}

async function init() {
  try {
    const fetchRequiredJson = async (path) => {
      const response = await fetch(path);
      if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
      return response.json();
    };
    const optionalFailures = [];
    const fetchOptionalJson = async (path, fallback) => {
      try {
        return await fetchRequiredJson(path);
      } catch (error) {
        optionalFailures.push(path);
        console.warn(`Optional data unavailable: ${path}`, error);
        return fallback;
      }
    };

    const [
      payload,
      universityPayload,
      programsPayload,
      predictionsPayload,
      monitorPayload,
      policiesPayload,
      coveragePayload,
      sourceMonitorPayload,
      programmeGroupsPayload,
      applicantCategoriesPayload,
    ] = await Promise.all([
      fetchRequiredJson("./data/applications.json"),
      fetchRequiredJson("./data/universities.json"),
      fetchRequiredJson("./data/programs.json"),
      fetchRequiredJson("./data/predictions.json"),
      fetchOptionalJson("./data/monitor-state.json", null),
      fetchOptionalJson("./data/window-policies.json", { policies: [] }),
      fetchOptionalJson("./data/coverage.json", null),
      fetchOptionalJson("./data/application-source-state.json", {
        applications: {},
      }),
      fetchOptionalJson("./data/programme-groups.json", { groups: [] }),
      fetchOptionalJson("./data/applicant-categories.json", {
        categories: [],
      }),
    ]);
    state.coverage = coveragePayload;
    state.sourceMonitor = sourceMonitorPayload.applications || {};
    state.universities = universityPayload.universities;
    state.programs = programsPayload.programs;
    state.programmeGroups = programmeGroupsPayload.groups || [];
    state.applicantCategoryLabels = Object.fromEntries(
      (applicantCategoriesPayload.categories || []).map((category) => [
        category.id,
        category.labelZh || category.labelEn || category.id,
      ]),
    );
    state.policies = policiesPayload.policies || [];
    const universityById = new Map(
      state.universities.map((university) => [university.id, university]),
    );
    const programById = new Map(
      state.programs.map((program) => [program.id, program]),
    );
    const groupById = new Map(
      state.programmeGroups.map((group) => [group.id, group]),
    );
    const enrichRecord = (record) => {
      const university = universityById.get(record.universityId) || {};
      const program =
        record.scopeType === "programme"
          ? programById.get(record.scopeId) || {}
          : {};
      const programmeGroup =
        record.scopeType === "programme-group"
          ? groupById.get(record.scopeId) || {}
          : {};
      return {
        ...record,
        sourceMonitor:
          state.sourceMonitor[record.basedOnRecordId || record.id] || {},
        school: university.school || record.school || "",
        schoolZh: university.schoolZh || record.schoolZh || "",
        qsRank: university.qsRank || record.qsRank || 999,
        country: university.country || record.country || "",
        region: university.region || record.region || "",
        program:
          program.name ||
          programmeGroup.name ||
          record.program ||
          (record.scopeType === "institution" ? "学校级默认窗口" : record.scopeId),
      };
    };
    const officialRecords = payload.applications.map((record) =>
      enrichRecord({ ...record, dataStatus: "official" }),
    );
    const predictedRecords = predictionsPayload.predictions.map((record) =>
      enrichRecord({ ...record, dataStatus: "predicted" }),
    );
    state.officialCount = officialRecords.length;
    state.predictionCount = predictedRecords.length;
    state.data = [...officialRecords, ...predictedRecords];
    state.universities.forEach((university) => {
      university.monitor = monitorPayload?.universities?.[university.id] || {};
    });
    const policyByUniversity = new Map(
      state.policies.map((policy) => [policy.universityId, policy]),
    );
    const coverageByUniversity = new Map(
      (state.coverage?.universities || []).map((item) => [
        item.universityId,
        item,
      ]),
    );
    state.universities.forEach((university) => {
      university.windowPolicy = policyByUniversity.get(university.id) || null;
      university.coverage = coverageByUniversity.get(university.id) || null;
    });
    state.meta = { ...payload.meta, ...universityPayload.meta };
    try {
      state.favorites = new Set(
        JSON.parse(localStorage.getItem("gradwindow:favorites") || "[]"),
      );
    } catch {
      state.favorites = new Set();
    }
    loadUrlState();

    populateSelect(
      "region-filter",
      uniqueSorted(
        [...state.data, ...state.universities].map((record) => record.region),
      ),
    );
    populateSelect(
      "intake-filter",
      uniqueSorted(state.data.map((record) => record.intake)),
    );
    const allowedStatuses = new Set([
      "all",
      "open",
      "upcoming",
      "predicted",
      "closed",
      "unknown",
    ]);
    if (!allowedStatuses.has(state.status)) state.status = "all";
    if (
      state.region !== "all" &&
      ![...document.getElementById("region-filter").options].some(
        (option) => option.value === state.region,
      )
    ) {
      state.region = "all";
    }
    if (
      state.intake !== "all" &&
      ![...document.getElementById("intake-filter").options].some(
        (option) => option.value === state.intake,
      )
    ) {
      state.intake = "all";
    }
    document.getElementById("search-input").value = state.search;
    document.getElementById("region-filter").value = state.region;
    document.getElementById("intake-filter").value = state.intake;
    document.querySelectorAll(".status-tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.status === state.status);
    });
    const schoolCount = state.universities.length;
    document.getElementById("total-schools").textContent = schoolCount;
    document.getElementById("total-records").textContent = state.officialCount;
    document.getElementById("total-predictions").textContent =
      state.predictionCount;
    const checkedAt = monitorPayload?.meta?.checkedAt;
    document.getElementById("updated-at").textContent = checkedAt
      ? `官网检查于 ${formatDate(checkedAt.slice(0, 10))}`
      : `正式数据更新于 ${formatDate(state.meta.updatedAt.slice(0, 10))}`;
    const monitorSummary = monitorPayload?.meta?.summary;
    document.getElementById("monitor-summary").textContent = monitorSummary
      ? ` 最近一次检查：${monitorSummary.ok}/${monitorSummary.total} 个页面可直接访问，${monitorSummary.blocked} 个页面限制自动访问。`
      : " 监控状态暂不可用，正式窗口数据仍可正常浏览。";
    if (optionalFailures.length) {
      document.getElementById("monitor-summary").textContent +=
        ` ${optionalFailures.length} 项辅助数据暂未加载。`;
    }
    document.getElementById("demo-banner").hidden = false;
    renderCoverage();
    setupHero();
    bindEvents();
    render();
  } catch (error) {
    const errorState = makeElement("div", { className: "empty-state" });
    errorState.append(
      makeElement("strong", { text: "数据加载失败" }),
      makeElement("span", {
        text: "请通过本地服务器或 GitHub Pages 打开本站。",
      }),
    );
    document.getElementById("application-groups").replaceChildren(errorState);
    console.error(error);
  }
}

init();
