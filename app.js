import { getApplicationStatus } from "./status.js";
import {
  canonicalIntake,
  compareIntakes,
  intakeLabel,
} from "./intake-filter.js";
import {
  countryLabel,
  programmeLabel,
  regionLabel,
  roundLabel,
  schoolLabels,
} from "./localization.js";

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
  top100Only: false,
  language: "en",
  theme: "light",
  monitorPayload: null,
  optionalFailureCount: 0,
};

const I18N = {
  en: {
    navTracker: "Application tracker", navMethod: "Methodology", navSources: "Sources",
    eyebrow: "Daily monitoring of global university application windows",
    heroTitle: "Never miss a<br /><em>master's deadline</em>",
    heroDescription: "Track master's application periods across QS Top 200 universities, organised by current status.",
    browseWindows: "Browse application windows", loadingData: "Loading data…",
    featureOfficial: "Official sources", featureDaily: "Daily checks", featureCalendar: "Add to calendar", featureRanked: "QS-ranked",
    trackerTitle: "Master's application windows", universities: "universities", officialWindows: "official windows", estimatedWindows: "estimated windows",
    dataRules: "Data policy", dataRulesText: "Official dates and historical estimates are kept separate. Estimates shift the most recent verified cycle by one calendar year and never count as official windows.",
    coverageTitle: "QS Top 200 data coverage", coverageDescription: "Admissions links, policies, programmes, and exact windows are measured separately.",
    coverageEntries: "official entries located", coveragePolicies: "date policies verified", coveragePrograms: "with representative programmes",
    coverageWindows: "with exact windows", coverageRecords: "official date records", coveragePredictions: "historical estimates",
    searchPlaceholder: "Search university, programme, or country", allRegions: "All regions", allIntakes: "All intakes",
    favoritesOnly: "Favourites only", top100Only: "QS Top 100 only", exportFavorites: "Export favourite deadlines",
    statusAll: "All", statusOpen: "Open now", statusUpcoming: "Opening soon", statusFuture: "Future", statusClosed: "Closed", statusDirectory: "University directory",
    emptyTitle: "No matching application windows", emptyText: "Adjust your search or filters and try again.",
    methodTitle: "Where do the dates come from?", method1Title: "Locate official pages", method1Text: "Each record links to an official university, faculty, or programme admissions page.",
    method2Title: "Check changes daily", method2Text: "Automated monitoring flags repeated page changes for human review.",
    method3Title: "Generate cycle estimates", method3Text: "When the next cycle is unpublished, the latest verified dates are shifted by one year and marked unofficial.",
    method4Title: "Replace with official dates", method4Text: "Verified new-cycle dates replace matching estimates automatically.",
    footerText: "Application dates may vary by programme and applicant category. Always confirm on the official university website.",
    openTitle: "Open now", openDescription: "Applications can currently be submitted",
    upcomingTitle: "Opening soon", upcomingDescription: "Opening within the next 30 days",
    futureTitle: "Future openings", futureDescription: "Opening more than 30 days from today",
    closedTitle: "Closed", closedDescription: "This application cycle has ended",
    directoryTitle: "University and programme directory", directoryDescription: "Browse admissions links, date policies, and current coverage",
    favorite: "Favourite", favorited: "Saved", removeFavorite: "Remove favourite",
    calendarShift: "Calendar-date shift", basedOn: "based on", daysAgo: "days ago", dueToday: "Due today", dueTomorrow: "Due tomorrow", daysLeft: "days left",
    allApplicants: "All applicants", sourceChanged: "Source page changed", sourceOk: "Source check passed", sourceBlocked: "Source blocks automated access", sourceError: "Source check failed", sourceUnchecked: "Source not checked",
    estimateBadge: "Based on previous cycle", viewReference: "View reference source ↗", viewOfficial: "View official source ↗", verifiedOn: "Verified", reference: "Reference",
    downloadIcs: "Download ICS calendar file", rank: "QS rank", university: "University", programme: "Programme", applicantGroup: "Applicant group",
    opens: "Opening date", deadline: "Deadline", calendar: "Calendar", source: "Source", estimatedOpen: "Estimated opening · unofficial", applicationsOpen: "Applications open",
    lowConfidence: "Low confidence", mediumConfidence: "Medium confidence", highConfidence: "High confidence", estimate: "Estimate", historicalCycles: "historical cycle(s)",
    windows: "windows", universityEntry: "University / application", programmeIntake: "Programme / intake", addCalendar: "Add to calendar", dataSource: "Data source",
    curatedEntry: "Curated entry", discoveredEntry: "Official page located", candidateEntry: "Candidate page pending review", homepageEntry: "Official homepage linked",
    pageChanged: "Page changed", checkOk: "Check passed", accessLimited: "Automated access limited", checkError: "Check failed", notChecked: "Not checked",
    policyPending: "Date policy pending", checkProgramme: "Check the programme page", published: "published", nextCycle: "Next cycle",
    programmeDeadline: "Programme-level deadlines", programmeVaries: "Dates may vary by programme", mixedPolicy: "Faculty rounds + programme exceptions", fillsEarly: "Some programmes close when full",
    sharedWindow: "Shared university window", categorySpecific: "Varies by applicant category", inheritedPolicy: "Inherited default window", programmeOverrides: "Programme exceptions may override it",
    broadMasters: "Broad master's offering", representativeAvailable: "Representative programme available", limitedMasters: "Limited master's offering", someNotDirect: "Some fields do not admit directly",
    unverified: "Not yet verified", inspectProgramme: "Check specific programmes", batch: "Batch", policies: "policies", programmes: "programmes", officialDates: "exact dates", predictions: "estimates",
    countries: "Country/region", mastersScope: "Master's scope", entryStatus: "Entry status", latestCheck: "Latest check", graduateApplication: "Graduate application",
    universityWebsite: "University website", dateNotes: "Date notes", openCandidate: "Open candidate page", openApplication: "Open application", programmeDirectoryRequired: "Use the programme directory",
    officialWebsite: "Official website ↗", schools: "universities", institutionWindow: "Institution-level default window",
    checkedAt: "Official pages checked", dataUpdatedAt: "Official data updated", monitorUnavailable: "Monitoring status is unavailable; official windows remain accessible.",
    pagesAccessible: "pages accessible", pagesBlocked: "pages block automated access", optionalUnavailable: "optional data source(s) unavailable",
    loadFailed: "Data failed to load", useServer: "Open this site through a local server or GitHub Pages.",
  },
  zh: {
    navTracker: "申请日历", navMethod: "数据说明", navSources: "来源覆盖",
    eyebrow: "每日监控全球名校申请窗口", heroTitle: "别让心仪项目的<br /><em>截止日期</em>悄悄溜走",
    heroDescription: "汇总 QS 前 200 大学硕士申请时间，按开放状态自动整理。找到项目、记住日期、直接申请。",
    browseWindows: "浏览申请窗口", loadingData: "正在读取数据…",
    featureOfficial: "官网来源", featureDaily: "每日检查", featureCalendar: "一键加日历", featureRanked: "QS 排名排序",
    trackerTitle: "硕士申请窗口", universities: "所大学", officialWindows: "个官网窗口", estimatedWindows: "个预测窗口",
    dataRules: "正式数据规则", dataRulesText: "官网日期与历史参考严格分层；参考日期只把最近一个已核验周期平移一年，不计入正式窗口。",
    coverageTitle: "QS 前 200 数据建设进度", coverageDescription: "入口、规则、项目与精确日期分开统计。",
    coverageEntries: "已定位官方入口", coveragePolicies: "已核验日期规则", coveragePrograms: "已有代表项目", coverageWindows: "已有精确窗口",
    coverageRecords: "正式日期记录", coveragePredictions: "历史周期预测", searchPlaceholder: "搜索大学、项目或国家/地区",
    allRegions: "所有地区", allIntakes: "所有入学季", favoritesOnly: "仅看收藏", top100Only: "仅看 QS 前100", exportFavorites: "导出收藏截止日",
    statusAll: "全部", statusOpen: "正在开放", statusUpcoming: "即将开放", statusFuture: "未来开放", statusClosed: "已截止", statusDirectory: "学校目录",
    emptyTitle: "没有匹配的申请窗口", emptyText: "调整搜索词或筛选条件后再试。", methodTitle: "日期来自哪里？",
    method1Title: "锁定官网页面", method1Text: "每条记录绑定学校、院系或项目的官方申请页面。", method2Title: "每日差异检查", method2Text: "自动任务检查页面变化，重复变化进入人工审核。",
    method3Title: "生成周期预测", method3Text: "下一周期尚无精确日期时，将最近一个官网周期平移一年并标为非官方。",
    method4Title: "官网自动替换", method4Text: "新周期日期核验后自动替代对应预测。", footerText: "申请日期可能随项目和申请人类别变化，请始终以学校官网为准。",
    openTitle: "正在开放", openDescription: "当前可以提交申请", upcomingTitle: "即将开放", upcomingDescription: "将在未来 30 天内开放",
    futureTitle: "未来开放", futureDescription: "开放日期距离今天超过 30 天", closedTitle: "当前已截止", closedDescription: "本轮申请已结束",
    directoryTitle: "学校与项目目录", directoryDescription: "查看全部学校入口、日期规则与当前覆盖情况", favorite: "收藏", favorited: "已收藏", removeFavorite: "取消收藏",
    calendarShift: "同日历日期平移", basedOn: "参考", daysAgo: "天前截止", dueToday: "今天截止", dueTomorrow: "明天截止", daysLeft: "天后截止",
    allApplicants: "所有申请人", sourceChanged: "来源页面有变化", sourceOk: "来源检查正常", sourceBlocked: "来源限制访问", sourceError: "来源检查异常", sourceUnchecked: "来源尚未检查",
    estimateBadge: "基于上周期预测", viewReference: "查看参考周期官网 ↗", viewOfficial: "查看官网 ↗", verifiedOn: "核验于", reference: "参考",
    downloadIcs: "下载 ICS 日历文件", rank: "QS 排名", university: "大学", programme: "项目", applicantGroup: "适用人群",
    opens: "开放日期", deadline: "截止日期", calendar: "日历", source: "来源", estimatedOpen: "预计开放 · 非官方", applicationsOpen: "开放申请",
    lowConfidence: "低置信度", mediumConfidence: "中置信度", highConfidence: "高置信度", estimate: "预测", historicalCycles: "个历史周期",
    windows: "个窗口", universityEntry: "大学 / 申请入口", programmeIntake: "项目 / 入学季", addCalendar: "添加日历", dataSource: "数据来源",
    curatedEntry: "人工核验入口", discoveredEntry: "官网自动定位", candidateEntry: "候选页待复核", homepageEntry: "官方主页已接入",
    pageChanged: "页面有变化", checkOk: "检查正常", accessLimited: "限制自动访问", checkError: "检查异常", notChecked: "尚未检查",
    policyPending: "待核验窗口粒度", checkProgramme: "打开具体项目后确认", published: "已发布", nextCycle: "下一周期",
    programmeDeadline: "项目级截止日", programmeVaries: "同校不同项目可能不同", mixedPolicy: "学院轮次 + 项目例外", fillsEarly: "部分课程招满即止",
    sharedWindow: "学校级共享窗口", categorySpecific: "按申请人类别分流", inheritedPolicy: "继承默认申请周期", programmeOverrides: "项目可覆盖例外日期",
    broadMasters: "广泛招收硕士", representativeAvailable: "可选择代表项目", limitedMasters: "硕士招生有限", someNotDirect: "部分方向不直接招收",
    unverified: "尚未核验", inspectProgramme: "需检查具体培养方向", batch: "第", policies: "规则", programmes: "项目", officialDates: "正式日期", predictions: "预测",
    countries: "国家/地区", mastersScope: "硕士范围", entryStatus: "入口状态", latestCheck: "最近监控", graduateApplication: "研究生申请",
    universityWebsite: "学校官网", dateNotes: "日期说明", openCandidate: "打开候选页", openApplication: "打开申请入口", programmeDirectoryRequired: "需从项目目录进入",
    officialWebsite: "官方网站 ↗", schools: "所大学", institutionWindow: "学校级默认窗口",
    checkedAt: "官网检查于", dataUpdatedAt: "正式数据更新于", monitorUnavailable: "监控状态暂不可用，正式窗口数据仍可正常浏览。",
    pagesAccessible: "个页面可直接访问", pagesBlocked: "个页面限制自动访问", optionalUnavailable: "项辅助数据暂未加载",
    loadFailed: "数据加载失败", useServer: "请通过本地服务器或 GitHub Pages 打开本站。",
  },
};

function t(key) {
  return I18N[state.language][key] || I18N.en[key] || key;
}

function statusLabels() {
  return {
    open: { title: t("openTitle"), description: t("openDescription") },
    upcoming: { title: t("upcomingTitle"), description: t("upcomingDescription") },
    future: { title: t("futureTitle"), description: t("futureDescription") },
    closed: { title: t("closedTitle"), description: t("closedDescription") },
    unknown: { title: t("directoryTitle"), description: t("directoryDescription") },
  };
}

function dateFormatter() {
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : "en-GB", {
    year: "numeric", month: "short", day: "numeric", timeZone: "UTC",
  });
}

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
    text: active ? t("favorited") : t("favorite"),
    title: active ? t("removeFavorite") : t("favorite"),
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
  return getApplicationStatus(record, today);
}

function daysUntil(dateValue) {
  return Math.ceil((parseDate(dateValue) - todayUtc()) / 86_400_000);
}

function formatDate(value) {
  return dateFormatter().format(parseDate(value));
}

function deadlineNote(record, status) {
  if (record.dataStatus === "predicted") {
    return `${t("calendarShift")} · ${t("basedOn")} ${record.sourceCycle}`;
  }
  const days = daysUntil(record.closesAt);
  if (status === "closed") return `${Math.abs(days)} ${t("daysAgo")}`;
  if (days === 0) return t("dueToday");
  if (days === 1) return t("dueTomorrow");
  if (days > 1 && days <= 30) return `${days} ${t("daysLeft")}`;
  return intakeLabel(canonicalIntake(record), state.language);
}

const APPLICANT_CATEGORY_LABELS = {
  all: { en: "All applicants", zh: "所有申请人" },
  "international-bachelors": { en: "International bachelor's degree", zh: "境外本科申请人" },
  esop: { en: "ESOP scholarship applicants", zh: "ESOP 奖学金申请人" },
  "direct-doctorate": { en: "Direct doctorate applicants", zh: "直博申请人" },
  "swiss-bachelors": { en: "Swiss bachelor's degree", zh: "瑞士高校本科申请人" },
  "requires-uk-study-visa": { en: "UK Student visa required", zh: "需要英国学生签证" },
  "does-not-require-uk-study-visa": { en: "No UK Student visa required", zh: "无需英国学生签证" },
};

function applicantCategoryText(categories = []) {
  return categories
    .map(
      (category) =>
        state.applicantCategoryLabels[category]?.[state.language] ||
        APPLICANT_CATEGORY_LABELS[category]?.[state.language] ||
        category,
    )
    .join("、");
}

function sourceMonitorDescription(record) {
  const monitor = record.sourceMonitor || {};
  if (monitor.changed) return [t("sourceChanged"), "candidate"];
  if (monitor.status === "ok") return [t("sourceOk"), "verified"];
  if (monitor.status === "blocked") return [t("sourceBlocked"), "candidate"];
  if (monitor.status === "error" || monitor.status === "http-error") {
    return [t("sourceError"), "homepage"];
  }
  return [t("sourceUnchecked"), "homepage"];
}

function googleCalendarUrl(record) {
  const start = record.closesAt.replaceAll("-", "");
  const endDate = parseDate(record.closesAt);
  endDate.setUTCDate(endDate.getUTCDate() + 1);
  const end = endDate.toISOString().slice(0, 10).replaceAll("-", "");
  const prefix = record.dataStatus === "predicted" ? "[ESTIMATE] " : "";
  const title = `${prefix}${record.school} ${record.program} application deadline`;
  const details = [
    record.dataStatus === "predicted"
      ? "Unofficial calendar-date estimate. Confirm on the official website before applying."
      : "",
    `Application: ${record.applicationUrl}`,
    `Source: ${record.sourceUrl}`,
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
    `SUMMARY:${escapeIcs(`${record.dataStatus === "predicted" ? "[ESTIMATE] " : ""}${record.school} ${record.program} application deadline`)}`,
    `DESCRIPTION:${escapeIcs(`${record.dataStatus === "predicted" ? "Unofficial calendar-date estimate. Confirm on the official website.\n" : ""}Application: ${record.applicationUrl}\nSource: ${record.sourceUrl}`)}`,
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

function populateSelect(elementId, values, labeler = (value) => value) {
  const select = document.getElementById(elementId);
  const selected = select.value;
  [...select.options].slice(1).forEach((option) => option.remove());
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labeler(value);
    select.appendChild(option);
  });
  select.value = [...select.options].some((option) => option.value === selected)
    ? selected
    : "all";
}

function populateIntakeSelect() {
  const select = document.getElementById("intake-filter");
  const selected = state.intake;
  select.replaceChildren();
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = t("allIntakes");
  select.appendChild(allOption);

  const intakes = new Map();
  state.data.forEach((record) => {
    const intake = canonicalIntake(record);
    intakes.set(intake.key, intake);
  });
  [...intakes.values()].sort(compareIntakes).forEach((intake) => {
    const option = document.createElement("option");
    option.value = intake.key;
    option.textContent = intakeLabel(intake, state.language);
    select.appendChild(option);
  });
  select.value = [...select.options].some(
    (option) => option.value === selected,
  )
    ? selected
    : "all";
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
      (state.intake === "all" ||
        canonicalIntake(record).key === state.intake) &&
      (!state.top100Only || record.qsRank <= 100) &&
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
      (!state.top100Only || university.qsPosition <= 100) &&
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
  const schoolText = schoolLabels(record, state.language);
  school.appendChild(
    makeLink(schoolText.primary, record.applicationUrl, "school-link"),
  );
  school.appendChild(
    makeElement("span", {
      className: "school-meta",
      text: [
        schoolText.secondary,
        countryLabel(record.country, state.language),
      ].filter(Boolean).join(" · "),
    }),
  );
  const intake = intakeLabel(canonicalIntake(record), state.language);
  const localizedRound = roundLabel(record.round, state.language);
  const programme = makeTextStack(
    programmeLabel(record.scopeId, record.program, state.language),
    `${intake}${localizedRound ? ` · ${localizedRound}` : ""}`,
  );
  const source = document.createDocumentFragment();
  const predicted = record.dataStatus === "predicted";
  const [sourceStatus, sourceClass] = predicted
    ? [t("estimateBadge"), "predicted"]
    : sourceMonitorDescription(record);
  source.append(
    makeLink(
      predicted ? t("viewReference") : t("viewOfficial"),
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
        ? `${t("reference")} ${record.sourceCycle} · ${predictionConfidenceText(record)}`
        : `${t("verifiedOn")} ${record.verifiedAt}`,
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
    title: t("downloadIcs"),
  });
  ics.type = "button";
  ics.addEventListener("click", () => downloadIcs(record));
  calendar.appendChild(ics);
  calendar.appendChild(makeFavoriteButton(favoriteKey("window", record.id)));

  row.append(
    makeCell(t("rank"), rank),
    makeCell(t("university"), school),
    makeCell(t("programme"), programme),
    makeCell(
      t("applicantGroup"),
      makeElement("span", {
        className: "applicant-category",
        text: applicantCategoryText(record.applicantCategories),
      }),
    ),
    makeCell(
      t("opens"),
      makeTextStack(
        formatDate(record.opensAt),
        predicted ? t("estimatedOpen") : t("applicationsOpen"),
      ),
    ),
    makeCell(t("deadline"), deadline),
    makeCell(t("calendar"), calendar),
    makeCell(t("source"), source),
  );
  return row;
}

function predictionConfidenceText(record) {
  const labels = { low: t("lowConfidence"), medium: t("mediumConfidence"), high: t("highConfidence") };
  return `${labels[record.confidence] || t("estimate")} · ${record.evidenceCycleCount} ${t("historicalCycles")}`;
}

function createGroup(status, records) {
  const heading = statusLabels()[status];
  const { section, tbody } = createTableSection(
    status,
    heading,
    `${records.length} ${t("windows")}`,
    [
      t("rank"),
      t("universityEntry"),
      t("programmeIntake"),
      t("applicantGroup"),
      t("opens"),
      t("deadline"),
      t("addCalendar"),
      t("dataSource"),
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
  if (status === "curated") return [t("curatedEntry"), "verified"];
  if (status === "discovered") return [t("discoveredEntry"), "discovered"];
  if (status === "low-confidence") return [t("candidateEntry"), "candidate"];
  return [t("homepageEntry"), "homepage"];
}

function monitorStatus(university) {
  const monitor = university.monitor || {};
  if (monitor.changed) return [t("pageChanged"), "candidate"];
  if (monitor.status === "ok") return [t("checkOk"), "verified"];
  if (monitor.status === "blocked") return [t("accessLimited"), "candidate"];
  if (monitor.status === "error" || monitor.status === "http-error") {
    return [t("checkError"), "homepage"];
  }
  return [t("notChecked"), "homepage"];
}

function policyDescription(university) {
  const policy = university.windowPolicy;
  if (!policy) return [t("policyPending"), t("checkProgramme")];
  const guidance = policy.cycleGuidance?.opensText;
  const windowCount = university.coverage?.windowCount || 0;
  const prefix = windowCount ? `${t("published")} ${windowCount} · ` : "";
  if (policy.model === "programme-specific") {
    return [
      t("programmeDeadline"),
      `${prefix}${guidance ? `${t("nextCycle")}: ${guidance}` : t("programmeVaries")}`,
    ];
  }
  if (policy.model === "mixed") {
    return [
      t("mixedPolicy"),
      `${prefix}${guidance ? `${t("nextCycle")}: ${guidance}` : t("fillsEarly")}`,
    ];
  }
  if (policy.model === "applicant-category") {
    return [
      t("sharedWindow"),
      `${prefix}${guidance ? `${t("nextCycle")}: ${guidance}` : t("categorySpecific")}`,
    ];
  }
  return [t("inheritedPolicy"), t("programmeOverrides")];
}

function mastersAvailabilityDescription(university) {
  const availability = university.windowPolicy?.mastersAvailability;
  if (availability === "broad") return [t("broadMasters"), t("representativeAvailable")];
  if (availability === "limited") {
    return [t("limitedMasters"), t("someNotDirect")];
  }
  return [t("unverified"), t("inspectProgramme")];
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

  document.getElementById("coverage-panel").hidden = false;
}

function createUniversityGroup(universities) {
  const heading = statusLabels().unknown;
  const { section, tbody } = createTableSection(
    "unknown",
    heading,
    `${universities.length} ${t("schools")}`,
    [
      t("rank"), t("university"), t("countries"), t("mastersScope"),
      t("entryStatus"), t("latestCheck"), t("graduateApplication"),
      t("universityWebsite"), t("dateNotes"),
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
          ? t("openCandidate")
          : t("openApplication");
      const row = document.createElement("tr");
      const schoolText = schoolLabels(university, state.language);
      const school = makeTextStack(
        schoolText.primary,
        schoolText.secondary,
      );
      const admissions = directUrl
        ? makeLink(directLabel, directUrl, "school-link")
        : makeElement("span", {
            className: "school-meta",
            text: t("programmeDirectoryRequired"),
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
        makeCell(t("rank"), makeElement("span", { className: "rank-cell", text: rankLabel })),
        makeCell(t("university"), school),
        makeCell(
          t("countries"),
          makeElement("span", {
            text: countryLabel(university.country, state.language),
          }),
        ),
        makeCell(t("mastersScope"), makeTextStack(mastersPrimary, mastersSecondary)),
        makeCell(t("entryStatus"), makeElement("span", { className: `source-badge ${statusClass}`, text: statusLabel })),
        makeCell(t("latestCheck"), makeElement("span", { className: `source-badge ${monitorClass}`, text: monitorLabel })),
        makeCell(t("graduateApplication"), actions),
        makeCell(t("universityWebsite"), makeLink(t("officialWebsite"), university.homepageUrl, "source-link")),
        makeCell(t("dateNotes"), makeTextStack(policyPrimary, policySecondary)),
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
    future: 0,
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

  ["open", "upcoming", "future", "closed"].forEach((status) => {
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
  if (state.top100Only) params.set("top", "100");
  history.replaceState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}${location.hash}`);
}

function loadUrlState() {
  const params = new URLSearchParams(location.search);
  state.search = params.get("q") || "";
  state.region = params.get("region") || "all";
  state.intake = params.get("intake") || "all";
  state.status = params.get("status") || "all";
  state.top100Only = params.get("top") === "100";
}

function updateFavoriteControls() {
  const count = state.favorites.size;
  document.getElementById("favorite-count").textContent = count;
  document
    .getElementById("favorites-toggle")
    .classList.toggle("active", state.favoritesOnly);
  document
    .getElementById("top100-toggle")
    .classList.toggle("active", state.top100Only);
  document.getElementById("export-favorites").disabled = !state.data.some(
    (record) => state.favorites.has(favoriteKey("window", record.id)),
  );
}

function applyStaticTranslations() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((node) => {
    node.innerHTML = t(node.dataset.i18nHtml);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  document.getElementById("language-toggle").textContent =
    state.language === "en" ? "中文" : "EN";
  document.getElementById("theme-toggle").textContent =
    state.theme === "dark"
      ? (state.language === "zh" ? "浅色" : "Light")
      : (state.language === "zh" ? "深色" : "Dark");
  document.title =
    state.language === "zh"
      ? "GradWindow · QS 200 硕士申请时间表"
      : "GradWindow · QS Top 200 Master's Applications";
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  localStorage.setItem("gradwindow:theme", state.theme);
  const button = document.getElementById("theme-toggle");
  if (button) {
    button.textContent =
      state.theme === "dark"
        ? (state.language === "zh" ? "浅色" : "Light")
        : (state.language === "zh" ? "深色" : "Dark");
  }
}

function updateDataNotes() {
  const checkedAt = state.monitorPayload?.meta?.checkedAt;
  document.getElementById("updated-at").textContent = checkedAt
    ? `${t("checkedAt")} ${formatDate(checkedAt.slice(0, 10))}`
    : `${t("dataUpdatedAt")} ${formatDate(state.meta.updatedAt.slice(0, 10))}`;
  const monitorSummary = state.monitorPayload?.meta?.summary;
  document.getElementById("monitor-summary").textContent = monitorSummary
    ? ` ${monitorSummary.ok}/${monitorSummary.total} ${t("pagesAccessible")}, ${monitorSummary.blocked} ${t("pagesBlocked")}.`
    : ` ${t("monitorUnavailable")}`;
  if (state.optionalFailureCount) {
    document.getElementById("monitor-summary").textContent +=
      ` ${state.optionalFailureCount} ${t("optionalUnavailable")}.`;
  }
}

function refreshLanguage() {
  localStorage.setItem("gradwindow:language", state.language);
  applyStaticTranslations();
  populateSelect(
    "region-filter",
    uniqueSorted(
      [...state.data, ...state.universities].map((record) => record.region),
    ),
    (region) => regionLabel(region, state.language),
  );
  populateIntakeSelect();
  updateDataNotes();
  renderCoverage();
  setupHero();
  render();
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
    document.getElementById("hero-deadline-month").textContent =
      state.language === "zh" ? "所学校" : "SCHOOLS";
    document.getElementById("hero-deadline-school").textContent =
      state.language === "zh" ? "官方申请目录" : "Official admissions directory";
    return;
  }
  const parts = shortDateFormatter
    .formatToParts(parseDate(futureDeadline.closesAt))
    .reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
  document.getElementById("hero-deadline-day").textContent = parts.day;
  document.getElementById("hero-deadline-month").textContent =
    parts.month.toUpperCase();
  document.getElementById("hero-deadline-school").textContent =
    schoolLabels(futureDeadline, state.language).primary;
}

function bindEvents() {
  document.getElementById("language-toggle").addEventListener("click", () => {
    state.language = state.language === "en" ? "zh" : "en";
    refreshLanguage();
  });
  document.getElementById("theme-toggle").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme();
  });
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
  document.getElementById("top100-toggle").addEventListener("click", () => {
    state.top100Only = !state.top100Only;
    syncUrl();
    render();
  });
  document
    .getElementById("export-favorites")
    .addEventListener("click", downloadFavoriteCalendars);
}

async function init() {
  try {
    state.language =
      localStorage.getItem("gradwindow:language") === "zh" ? "zh" : "en";
    const savedTheme = localStorage.getItem("gradwindow:theme");
    state.theme = ["light", "dark"].includes(savedTheme)
      ? savedTheme
      : window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    applyTheme();
    applyStaticTranslations();
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
    state.monitorPayload = monitorPayload;
    state.optionalFailureCount = optionalFailures.length;
    state.sourceMonitor = sourceMonitorPayload.applications || {};
    state.universities = universityPayload.universities;
    state.programs = programsPayload.programs;
    state.programmeGroups = programmeGroupsPayload.groups || [];
    state.applicantCategoryLabels = Object.fromEntries(
      (applicantCategoriesPayload.categories || []).map((category) => [
        category.id,
        {
          en: category.labelEn || category.id,
          zh: category.labelZh || category.labelEn || category.id,
        },
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
          (record.scopeType === "institution" ? t("institutionWindow") : record.scopeId),
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
      (region) => regionLabel(region, state.language),
    );
    const legacyIntake = state.intake;
    const matchingLegacyRecord = state.data.find(
      (record) => record.intake === legacyIntake,
    );
    if (matchingLegacyRecord) {
      state.intake = canonicalIntake(matchingLegacyRecord).key;
    }
    populateIntakeSelect();
    const allowedStatuses = new Set([
      "all",
      "open",
      "upcoming",
      "future",
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
    updateDataNotes();
    document.getElementById("demo-banner").hidden = false;
    renderCoverage();
    setupHero();
    bindEvents();
    render();
  } catch (error) {
    const errorState = makeElement("div", { className: "empty-state" });
    errorState.append(
      makeElement("strong", { text: t("loadFailed") }),
      makeElement("span", {
        text: t("useServer"),
      }),
    );
    document.getElementById("application-groups").replaceChildren(errorState);
    console.error(error);
  }
}

init();
