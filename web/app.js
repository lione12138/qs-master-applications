import { countUniversitiesByStatus, getApplicationStatus } from "./status.js";
import { state } from "./state.js";
import { t } from "./strings.js";
import { makeCalendarMenu } from "./calendar-export.js";
import {
  initAuth,
  openAuthPanel,
  scheduleFavoriteSync,
  setupAuthPanel,
  updateAuthUi,
} from "./auth.js";
import {
  makeReviewButton,
  setupReviewPanel,
  updateReviewAuthState,
} from "./review.js";
import {
  acronym,
  formatDateRange,
  makeElement,
  makeLink,
  parseDate,
  safeUrl,
} from "./dom.js";
import {
  canonicalIntake,
  compareIntakes,
  intakeLabel,
} from "./intake-filter.js";
import {
  countryLabel,
  programmeLabel,
  programmeSearchTerms,
  regionLabel,
  roundLabel,
  schoolLabels,
  setProgrammeTranslations,
} from "./localization.js";
import { needsManualCheck } from "./exception-status.js";
import {
  createRankingIndex,
  filterRecordsToRanking,
} from "./ranking-filter.js";
import { groupWindowRecordsForDisplay } from "./window-grouping.js";

const PAGE_SIZE = 20;
const dateFormatters = new Map();
const deadlineDatePartsFormatters = new Map();
const recordSearchTextCache = new WeakMap();
const recordIntakeCache = new WeakMap();
let selectedRankingCache = null;

function statusLabels() {
  return {
    open: { title: t("openTitle"), description: t("openDescription") },
    upcoming: {
      title: t("upcomingTitle"),
      description: t("upcomingDescription"),
    },
    future: { title: t("futureTitle"), description: t("futureDescription") },
    closed: { title: t("closedTitle"), description: t("closedDescription") },
    exception: {
      title: t("exceptionTitle"),
      description: t("exceptionDescription"),
    },
    unknown: {
      title: t("directoryTitle"),
      description: t("directoryDescription"),
    },
  };
}

function dateFormatter() {
  const locale = state.language === "zh" ? "zh-CN" : "en-GB";
  if (!dateFormatters.has(locale)) {
    dateFormatters.set(
      locale,
      new Intl.DateTimeFormat(locale, {
        year: "numeric",
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      }),
    );
  }
  return dateFormatters.get(locale);
}

function deadlineDatePartsFormatter() {
  const locale = state.language === "zh" ? "zh-CN" : "en-GB";
  if (!deadlineDatePartsFormatters.has(locale)) {
    deadlineDatePartsFormatters.set(
      locale,
      new Intl.DateTimeFormat(locale, {
        day: "2-digit",
        month: "short",
        timeZone: "UTC",
      }),
    );
  }
  return deadlineDatePartsFormatters.get(locale);
}

function makeCell(label, ...children) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  children.filter(Boolean).forEach((child) => cell.appendChild(child));
  return cell;
}

function resetPages() {
  state.pages = {};
  state.expandedWindowGroups.clear();
  state.expandedUniversityGroups.clear();
}

function makeTextStack(primary, secondary, primaryClass = "date-primary") {
  const wrapper = document.createDocumentFragment();
  wrapper.appendChild(
    makeElement("span", { className: primaryClass, text: primary }),
  );
  if (secondary) {
    wrapper.appendChild(
      makeElement("span", { className: "date-secondary", text: secondary }),
    );
  }
  return wrapper;
}

function makeLinkedTextStack(
  primary,
  url,
  secondary,
  primaryClass = "date-primary",
) {
  const wrapper = document.createDocumentFragment();
  wrapper.appendChild(makeLink(primary, url, primaryClass));
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
  localStorage.setItem(
    "gradwindow:favorites",
    JSON.stringify([...state.favorites]),
  );
  updateFavoriteControls();
  scheduleFavoriteSync();
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
  button.dataset.favoriteKey = key;
  button.setAttribute("aria-pressed", String(active));
  button.addEventListener("click", () => toggleFavorite(key));
  return button;
}

function todayUtc() {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
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

function makeSchoolDisplay(record) {
  const school = document.createDocumentFragment();
  const schoolText = schoolLabels(record, state.language);
  const country = countryLabel(record.country, state.language);
  school.appendChild(
    makeLink(schoolText.primary, record.applicationUrl, "school-link"),
  );
  if (country) {
    school.appendChild(
      makeElement("span", {
        className: "school-country-inline",
        text: `(${country})`,
      }),
    );
  }
  school.appendChild(
    makeElement("span", {
      className: "school-meta",
      text: [schoolText.secondary, country].filter(Boolean).join(" · "),
    }),
  );
  return school;
}

function makeResponsiveDeadline(
  opensAt,
  closesAt,
  secondary,
  primaryClass = "date-primary",
) {
  const deadline = document.createDocumentFragment();
  const desktop = makeElement("span", {
    className: "desktop-deadline-stack",
  });
  desktop.appendChild(
    makeTextStack(formatDate(closesAt), secondary, primaryClass),
  );
  deadline.append(
    desktop,
    makeElement("span", {
      className: `mobile-date-range ${primaryClass}`,
      text: formatDateRange(opensAt, closesAt),
    }),
  );
  return deadline;
}

function recordIntake(record) {
  if (!recordIntakeCache.has(record)) {
    recordIntakeCache.set(record, canonicalIntake(record));
  }
  return recordIntakeCache.get(record);
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
  return intakeLabel(recordIntake(record), state.language);
}

const APPLICANT_CATEGORY_LABELS = {
  all: { en: "All applicants", zh: "所有申请人" },
  "international-bachelors": {
    en: "International bachelor's degree",
    zh: "境外本科申请人",
  },
  esop: { en: "ESOP scholarship applicants", zh: "ESOP 奖学金申请人" },
  "direct-doctorate": { en: "Direct doctorate applicants", zh: "直博申请人" },
  "swiss-bachelors": {
    en: "Swiss bachelor's degree",
    zh: "瑞士高校本科申请人",
  },
  "requires-uk-study-visa": {
    en: "UK Student visa required",
    zh: "需要英国学生签证",
  },
  "does-not-require-uk-study-visa": {
    en: "No UK Student visa required",
    zh: "无需英国学生签证",
  },
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

function closeWindowDetail() {
  const panel = document.getElementById("window-detail-panel");
  if (panel) panel.hidden = true;
  document.body.classList.remove("window-detail-open");
}

function detailField(label, value) {
  const row = makeElement("div", { className: "window-detail-field" });
  row.append(
    makeElement("span", { text: label }),
    makeElement("strong", { text: value }),
  );
  return row;
}

function openWindowDetail(record, status = getStatus(record)) {
  const panel = document.getElementById("window-detail-panel");
  const body = document.getElementById("window-detail-body");
  const actions = document.getElementById("window-detail-header-actions");
  const university = state.universityById.get(record.universityId);
  if (!panel || !body || !actions) return;

  const schoolText = schoolLabels(record, state.language);
  const intake = intakeLabel(recordIntake(record), state.language);
  const localizedRound = roundLabel(record.round, state.language);
  const programmeName = programmeLabel(
    record.scopeId,
    record.program,
    state.language,
  );
  const [sourceStatus, sourceClass] =
    record.dataStatus === "predicted"
      ? [t("estimateBadge"), "predicted"]
      : sourceMonitorDescription(record);

  const heading = makeElement("section", {
    className: "window-detail-heading",
  });
  const schoolRow = makeElement("div", {
    className: "window-detail-school-row",
  });
  schoolRow.append(
    makeElement("h2", { text: schoolText.primary }),
    makeElement("span", {
      className: "rank-cell",
      text: formatRank(
        selectedRankForUniversity(record.universityId)?.rankDisplay ||
          record.qsRank,
      ),
    }),
  );
  heading.append(
    schoolRow,
    makeElement("p", {
      className: "school-meta",
      text: [schoolText.secondary, countryLabel(record.country, state.language)]
        .filter(Boolean)
        .join(" · "),
    }),
    makeLink(
      programmeName,
      record.applicationUrl,
      "program-link window-detail-programme",
    ),
  );

  const deadline = makeElement("section", {
    className: "window-detail-deadline",
  });
  deadline.append(
    makeElement("span", { text: t("deadline") }),
    makeElement("strong", { text: formatDate(record.closesAt) }),
    makeElement("small", { text: deadlineNote(record, status) }),
  );

  const info = makeElement("section", { className: "window-detail-section" });
  info.append(
    makeElement("h3", { text: t("mobileWindowDetails") }),
    detailField(t("opens"), formatDate(record.opensAt)),
    detailField(
      t("programmeIntake"),
      `${intake}${localizedRound ? ` · ${localizedRound}` : ""}`,
    ),
    detailField(
      t("applicantGroup"),
      applicantCategoryText(record.applicantCategories),
    ),
    detailField(t("statusTabsLabel"), statusLabels()[status]?.title || status),
  );

  const source = makeElement("section", {
    className: "window-detail-section window-detail-source",
  });
  const sourceHeader = makeElement("div", {
    className: "window-detail-source-header",
  });
  sourceHeader.append(
    makeElement("h3", { text: t("dataSource") }),
    makeElement("span", {
      className: `source-badge ${sourceClass}`,
      text: sourceStatus,
    }),
  );
  source.append(
    sourceHeader,
    makeElement("p", {
      text:
        record.dataStatus === "predicted"
          ? `${t("reference")} ${record.sourceCycle} · ${predictionConfidenceText(record)}`
          : `${t("verifiedOn")} ${record.verifiedAt}`,
    }),
    makeLink(
      record.dataStatus === "predicted"
        ? t("viewReference")
        : t("viewOfficial"),
      record.sourceUrl,
      "primary-button window-detail-source-link",
    ),
  );

  if (university) {
    const reviews = makeElement("section", {
      className: "window-detail-section window-detail-reviews",
    });
    reviews.append(
      makeElement("h3", { text: t("schoolReviewsTitle") }),
      makeElement("p", { text: t("reviewPublicNote") }),
      makeReviewButton(university),
    );
    body.replaceChildren(heading, deadline, info, source, reviews);
  } else {
    body.replaceChildren(heading, deadline, info, source);
  }

  actions.replaceChildren(
    makeCalendarMenu(record),
    makeFavoriteButton(favoriteKey("window", record.id)),
  );
  panel.hidden = false;
  document.body.classList.add("window-detail-open");
  panel.querySelector("[data-window-detail-close]")?.focus();
}

function setupWindowDetailPanel() {
  document.querySelectorAll("[data-window-detail-close]").forEach((button) => {
    button.addEventListener("click", closeWindowDetail);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeWindowDetail();
  });
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
  recordsInSelectedRanking().forEach((record) => {
    const intake = recordIntake(record);
    if (intake.term === "academic") return;
    intakes.set(intake.key, intake);
  });
  [...intakes.values()].sort(compareIntakes).forEach((intake) => {
    const option = document.createElement("option");
    option.value = intake.key;
    option.textContent = intakeLabel(intake, state.language);
    select.appendChild(option);
  });
  select.value = [...select.options].some((option) => option.value === selected)
    ? selected
    : "all";
}

function buildSelectedRankingDefinition() {
  if (state.ranking === "qs") {
    return {
      id: "qs",
      shortLabel: "QS",
      available: true,
      rows: state.universities.map((university) => ({
        id: university.id,
        universityId: university.id,
        school: university.school,
        schoolZh: university.schoolZh,
        schoolAliasesZh: university.schoolAliasesZh || [],
        country: university.country,
        region: university.region,
        rankPosition: university.qsPosition,
        rankDisplay: university.rankDisplay,
        rankingOnly: false,
      })),
    };
  }
  const ranking = state.rankingPayload.rankings?.[state.ranking];
  if (!ranking) {
    return { id: state.ranking, available: false, rows: [] };
  }
  return { id: state.ranking, available: true, rows: [], ...ranking };
}

function selectedRankingContext() {
  if (
    selectedRankingCache?.ranking === state.ranking &&
    selectedRankingCache.universities === state.universities &&
    selectedRankingCache.rankingPayload === state.rankingPayload
  ) {
    return selectedRankingCache;
  }
  const definition = buildSelectedRankingDefinition();
  const rows = definition.available === false ? [] : definition.rows || [];
  selectedRankingCache = {
    ranking: state.ranking,
    universities: state.universities,
    rankingPayload: state.rankingPayload,
    definition,
    index: createRankingIndex(rows),
  };
  return selectedRankingCache;
}

function selectedRankingDefinition() {
  return selectedRankingContext().definition;
}

function selectedRankingRows() {
  return selectedRankingContext().index.rows;
}

function selectedRankByUniversityId() {
  return selectedRankingContext().index.byUniversityId;
}

function selectedRankForUniversity(universityId) {
  return selectedRankByUniversityId().get(universityId) || null;
}

function recordsInSelectedRanking() {
  const context = selectedRankingContext();
  if (context.recordsSource !== state.data) {
    context.recordsSource = state.data;
    context.records = filterRecordsToRanking(
      state.data,
      context.index.rows,
      context.index.universityIds,
    );
  }
  return context.records;
}

function selectedDirectoryUniversities() {
  return selectedRankingRows().map((rankingRow) => {
    const university = rankingRow.universityId
      ? state.universityById.get(rankingRow.universityId)
      : null;
    if (university) {
      return {
        ...university,
        rankPosition: rankingRow.rankPosition,
        rankDisplay: rankingRow.rankDisplay,
        rankingSourceUrl: rankingRow.sourceUrl || "",
        rankingOnly: false,
      };
    }
    return {
      id: `${state.ranking}:${rankingRow.id}`,
      school: rankingRow.school,
      schoolZh: rankingRow.schoolZh || "",
      schoolAliasesZh: rankingRow.schoolAliasesZh || [],
      country: rankingRow.country,
      region: rankingRow.region,
      rankPosition: rankingRow.rankPosition,
      rankDisplay: rankingRow.rankDisplay,
      rankingSourceUrl: rankingRow.sourceUrl || "",
      rankingOnly: true,
      admissionsDiscovery: "ranking-only",
      admissionsUrl: "",
      homepageUrl: "",
      monitor: {},
      windowPolicy: null,
      coverage: null,
    };
  });
}

function rankingShortLabel() {
  return selectedRankingDefinition().shortLabel || "QS";
}

function rankColumnLabel() {
  return `${rankingShortLabel()} ${t("rank")}`;
}

function rankRangeLabel(limit) {
  return t("rankRangeTop")
    .replace("{ranking}", rankingShortLabel())
    .replace("{limit}", limit);
}

function formatRank(rankDisplay) {
  return String(rankDisplay).startsWith("=") ? rankDisplay : `#${rankDisplay}`;
}

function refreshFilterOptions() {
  populateSelect(
    "region-filter",
    uniqueSorted(
      [...recordsInSelectedRanking(), ...selectedDirectoryUniversities()]
        .map((record) => record.region)
        .filter(Boolean),
    ),
    (region) => regionLabel(region, state.language),
  );
  populateIntakeSelect();
}

function updateRankingAvailability() {
  const select = document.getElementById("ranking-filter");
  [...select.options].forEach((option) => {
    if (option.value === "qs") return;
    const ranking = state.rankingPayload.rankings?.[option.value];
    option.disabled =
      !ranking || ranking.available === false || !ranking.rows?.length;
  });
}

function updateRankRangeOptions() {
  const rankRangeSelect = document.getElementById("rank-range-filter");
  if (!rankRangeSelect) return;
  [...rankRangeSelect.options].forEach((option) => {
    option.textContent = rankRangeLabel(option.value);
  });
  rankRangeSelect.value = [...rankRangeSelect.options].some(
    (option) => option.value === state.rankLimit,
  )
    ? state.rankLimit
    : "200";
}

function recordSearchText(record) {
  if (!recordSearchTextCache.has(record)) {
    recordSearchTextCache.set(
      record,
      [
        record.school,
        record.schoolZh,
        ...(record.schoolAliasesZh || []),
        acronym(record.school),
        record.program,
        ...programmeSearchTerms(record.scopeId, record.program),
        record.universityId,
        record.scopeId,
        record.country,
        record.region,
      ]
        .join(" ")
        .toLocaleLowerCase("zh-CN"),
    );
  }
  return recordSearchTextCache.get(record);
}

function filteredRecords() {
  const query = state.search.trim().toLocaleLowerCase("zh-CN");
  return recordsInSelectedRanking().filter((record) => {
    return (
      (!query || recordSearchText(record).includes(query)) &&
      (state.region === "all" || record.region === state.region) &&
      (state.intake === "all" || recordIntake(record).key === state.intake) &&
      (selectedRankForUniversity(record.universityId)?.rankPosition || 999) <=
        Number(state.rankLimit) &&
      (!state.favoritesOnly ||
        state.favorites.has(favoriteKey("window", record.id)))
    );
  });
}

function filteredUniversities() {
  const query = state.search.trim().toLocaleLowerCase("zh-CN");
  if (state.intake !== "all") return [];
  return selectedDirectoryUniversities().filter((university) => {
    const searchable = [
      university.school,
      university.schoolZh,
      ...(university.schoolAliasesZh || []),
      acronym(university.school),
      university.id,
      university.country,
      university.region,
    ]
      .join(" ")
      .toLocaleLowerCase("zh-CN");
    return (
      (!query || searchable.includes(query)) &&
      (state.region === "all" || university.region === state.region) &&
      university.rankPosition <= Number(state.rankLimit) &&
      (!state.favoritesOnly ||
        state.favorites.has(favoriteKey("university", university.id)))
    );
  });
}

function compareRecords(a, b) {
  const rankPosition = (record) =>
    selectedRankForUniversity(record.universityId)?.rankPosition || 999;
  const byRank = () =>
    rankPosition(a) - rankPosition(b) || a.closesAt.localeCompare(b.closesAt);
  if (state.sort === "opens") {
    return (
      a.opensAt.localeCompare(b.opensAt) ||
      a.closesAt.localeCompare(b.closesAt) ||
      rankPosition(a) - rankPosition(b)
    );
  }
  if (state.sort === "deadline") {
    return (
      a.closesAt.localeCompare(b.closesAt) ||
      a.opensAt.localeCompare(b.opensAt) ||
      rankPosition(a) - rankPosition(b)
    );
  }
  return byRank();
}

function hasActiveSearch() {
  return state.search.trim().length > 0;
}

function activeNonStatusFilter() {
  return (
    hasActiveSearch() ||
    state.ranking !== "qs" ||
    state.region !== "all" ||
    state.intake !== "all" ||
    state.rankLimit !== "200" ||
    state.favoritesOnly
  );
}

function localizedCount(count, labelKey) {
  return state.language === "zh"
    ? `${count}${t(labelKey)}`
    : `${count} ${t(labelKey)}`;
}

function syncFilterInputs() {
  document.getElementById("search-input").value = state.search;
  document.getElementById("ranking-filter").value = state.ranking;
  refreshFilterOptions();
  document.getElementById("region-filter").value = state.region;
  document.getElementById("intake-filter").value = state.intake;
  updateRankRangeOptions();
}

function resetFilter(filter) {
  if (filter === "search") state.search = "";
  if (filter === "ranking") {
    state.ranking = "qs";
    state.region = "all";
    state.intake = "all";
  }
  if (filter === "region") state.region = "all";
  if (filter === "intake") state.intake = "all";
  if (filter === "rankLimit") state.rankLimit = "200";
  if (filter === "favorites") state.favoritesOnly = false;
  syncFilterInputs();
  resetPages();
  syncUrl();
  render();
}

function clearFilters() {
  state.search = "";
  state.ranking = "qs";
  state.region = "all";
  state.intake = "all";
  state.rankLimit = "200";
  state.favoritesOnly = false;
  syncFilterInputs();
  resetPages();
  syncUrl();
  render();
}

function activeFilterItems() {
  const items = [];
  if (state.search.trim()) {
    items.push({
      key: "search",
      label: `${t("searchFilterChip")}: ${state.search.trim()}`,
    });
  }
  if (state.ranking !== "qs") {
    items.push({
      key: "ranking",
      label:
        document.getElementById("ranking-filter").selectedOptions[0]
          ?.textContent || rankingShortLabel(),
    });
  }
  if (state.region !== "all") {
    items.push({
      key: "region",
      label: regionLabel(state.region, state.language),
    });
  }
  if (state.intake !== "all") {
    items.push({
      key: "intake",
      label:
        document.getElementById("intake-filter").selectedOptions[0]
          ?.textContent || state.intake,
    });
  }
  if (state.rankLimit !== "200") {
    items.push({ key: "rankLimit", label: rankRangeLabel(state.rankLimit) });
  }
  if (state.favoritesOnly) {
    items.push({ key: "favorites", label: t("favoritesOnly") });
  }
  return items;
}

function makeFilterChip(item) {
  const button = makeElement("button", {
    className: "active-filter-chip",
    title: `${t("clearFilters")}: ${item.label}`,
  });
  button.type = "button";
  button.append(
    makeElement("span", { text: item.label }),
    makeElement("span", { className: "active-filter-chip-remove", text: "×" }),
  );
  button.addEventListener("click", () => resetFilter(item.key));
  return button;
}

function updateResultsToolbar(records, universities, exceptionUniversities) {
  const universityIds = new Set(
    records.map((record) => record.universityId).filter(Boolean),
  );
  if (state.status === "exception") {
    exceptionUniversities.forEach((university) =>
      universityIds.add(university.id),
    );
  }
  if (state.status === "unknown" || hasActiveSearch()) {
    universities.forEach((university) => universityIds.add(university.id));
  }
  document.getElementById("results-school-count").textContent = localizedCount(
    universityIds.size,
    "universitiesShown",
  );
  document.getElementById("results-window-count").textContent = windowCountText(
    records.length,
  );

  const chipContainer = document.getElementById("active-filter-chips");
  const filters = activeFilterItems();
  chipContainer.replaceChildren(...filters.map(makeFilterChip));
  if (filters.length) {
    const clearButton = makeElement("button", {
      className: "clear-filter-button",
      text: t("clearFilters"),
    });
    clearButton.type = "button";
    clearButton.addEventListener("click", clearFilters);
    chipContainer.appendChild(clearButton);
    chipContainer.setAttribute("aria-label", t("activeFilters"));
  } else {
    chipContainer.removeAttribute("aria-label");
  }

  const groupRows = [
    ...document.querySelectorAll(".university-group-parent[data-group-key]"),
  ];
  const groupActions = document.getElementById("group-view-actions");
  groupActions.hidden = groupRows.length === 0;
  if (groupRows.length) {
    const expandedCount = groupRows.filter(
      (row) => row.dataset.groupState === "expanded",
    ).length;
    document.getElementById("expand-visible-groups").disabled =
      expandedCount === groupRows.length;
    document.getElementById("collapse-visible-groups").disabled =
      expandedCount === 0;
  }
}

function setVisibleUniversityGroups(expanded) {
  document
    .querySelectorAll(".university-group-parent[data-group-key]")
    .forEach((row) => {
      if (expanded) state.expandedUniversityGroups.add(row.dataset.groupKey);
      else state.expandedUniversityGroups.delete(row.dataset.groupKey);
    });
  render();
}

function updateStatusTabs(focusStatus = "") {
  document.querySelectorAll(".status-tab").forEach((tab) => {
    const active = tab.dataset.status === state.status;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    if (focusStatus && tab.dataset.status === focusStatus) {
      tab.focus();
      tab.scrollIntoView({ block: "nearest", inline: "center" });
    }
  });
}

function recordsForCurrentView(baseRecords) {
  if (hasActiveSearch()) return baseRecords;
  return baseRecords.filter((record) => getStatus(record) === state.status);
}

function createRow(record, status, windowGroup = null) {
  const row = document.createElement("tr");
  row.className = "window-card-row";
  row.tabIndex = 0;
  row.dataset.detailHint = t("mobileCardHint");
  const days = daysUntil(record.closesAt);
  const deadlineClass =
    status === "open" && days >= 0 && days <= 14 ? "deadline-soon" : "";

  const rank = makeElement("span", {
    className: "rank-cell",
    text: formatRank(
      selectedRankForUniversity(record.universityId)?.rankDisplay ||
        record.qsRank,
    ),
  });
  const school = makeSchoolDisplay(record);
  const intake = intakeLabel(recordIntake(record), state.language);
  const localizedRound = roundLabel(record.round, state.language);
  const programme = makeLinkedTextStack(
    programmeLabel(record.scopeId, record.program, state.language),
    record.applicationUrl,
    `${intake}${localizedRound ? ` · ${localizedRound}` : ""}`,
    "program-link date-primary",
  );
  if (windowGroup?.collapsible) {
    row.classList.add("window-group-parent");
    const expanded = state.expandedWindowGroups.has(windowGroup.key);
    const hiddenCount = windowGroup.records.length - 1;
    const toggle = makeElement("button", {
      className: "window-group-toggle",
      text: expanded
        ? t("collapseSameDatePrograms")
        : `${t("expandSameDatePrograms")} ${hiddenCount} ${t("moreProgrammes")}`,
      title: expanded
        ? t("collapseSameDatePrograms")
        : `${t("expandSameDatePrograms")} ${hiddenCount} ${t("moreProgrammes")}`,
    });
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      if (expanded) state.expandedWindowGroups.delete(windowGroup.key);
      else state.expandedWindowGroups.add(windowGroup.key);
      render();
    });
    programme.appendChild(toggle);
  }
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
  const deadline = makeResponsiveDeadline(
    record.opensAt,
    record.closesAt,
    deadlineNote(record, status),
    `date-primary ${deadlineClass}`.trim(),
  );
  const calendar = makeCalendarMenu(record);
  const favorite = makeFavoriteButton(favoriteKey("window", record.id));
  const university = state.universityById.get(record.universityId);
  const cardActions = makeElement("div", { className: "mobile-card-actions" });
  cardActions.appendChild(favorite);
  if (university) cardActions.appendChild(makeReviewButton(university));

  const openDetails = (event) => {
    if (!window.matchMedia("(max-width: 720px)").matches) return;
    if (event.target.closest("a, button, details, input, select")) return;
    openWindowDetail(record, status);
  };
  row.addEventListener("click", openDetails);
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openDetails(event);
    }
  });

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
    makeCell(t("favorite"), cardActions),
    makeCell(t("source"), source),
  );
  return row;
}

function windowCountText(count) {
  return `${count} ${t("windows")}`;
}

function programmeCountText(count) {
  return `${count} ${t("programmes")}`;
}

function createUniversityGroupRow(universityGroup, status) {
  const representative = universityGroup.records[0];
  const row = document.createElement("tr");
  const expanded = state.expandedUniversityGroups.has(universityGroup.key);
  row.className = `window-card-row university-group-parent university-group-parent--${
    expanded ? "expanded" : "collapsed"
  }`;
  row.dataset.groupKey = universityGroup.key;
  row.dataset.groupState = expanded ? "expanded" : "collapsed";
  const records = universityGroup.records;
  const rank = makeElement("span", {
    className: "rank-cell",
    text: formatRank(
      selectedRankForUniversity(representative.universityId)?.rankDisplay ||
        representative.qsRank,
    ),
  });
  const school = makeSchoolDisplay(representative);

  const programmes = new Set(records.map((record) => record.scopeId));
  const programmeSummary = makeElement("div", {
    className: "school-group-summary",
  });
  const summaryHeading = makeElement("div", {
    className: "school-group-summary-heading",
  });
  summaryHeading.append(
    makeElement("span", {
      className: "school-group-kicker",
      text: t("schoolWindowGroup"),
    }),
    makeElement("span", {
      className: "school-group-state",
      text: expanded ? t("schoolGroupExpanded") : t("schoolGroupCollapsed"),
    }),
  );
  const summaryCounts = makeElement("div", {
    className: "school-group-counts",
  });
  summaryCounts.append(
    makeElement("strong", {
      className: "school-group-programme-count",
      text: programmeCountText(programmes.size),
    }),
    makeElement("span", {
      className: "school-group-window-count",
      text: windowCountText(records.length),
    }),
  );
  const toggle = makeElement("button", {
    className: "window-group-toggle university-group-toggle",
    title: expanded
      ? t("collapseSchoolWindows")
      : `${t("expandSchoolWindows")} ${programmeCountText(programmes.size)}`,
  });
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.append(
    makeElement("span", {
      text: expanded
        ? t("collapseSchoolWindows")
        : `${t("expandSchoolWindows")} ${programmeCountText(programmes.size)}`,
    }),
    makeElement("span", {
      className: "school-group-chevron",
      text: "›",
    }),
  );
  const toggleGroup = () => {
    if (expanded) state.expandedUniversityGroups.delete(universityGroup.key);
    else state.expandedUniversityGroups.add(universityGroup.key);
    render();
  };
  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleGroup();
  });
  programmeSummary.append(summaryHeading, summaryCounts, toggle);
  row.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) return;
    toggleGroup();
  });

  const earliestOpen = records
    .map((record) => record.opensAt)
    .filter(Boolean)
    .sort()[0];
  const nearestDeadline = [...records].sort((a, b) =>
    a.closesAt.localeCompare(b.closesAt),
  )[0];
  const source = makeElement("span", {
    className: "source-badge discovered school-group-source",
    text: `${windowCountText(records.length)} · ${t("groupedBySchool")}`,
  });

  row.append(
    makeCell(t("rank"), rank),
    makeCell(t("university"), school),
    makeCell(t("programme"), programmeSummary),
    makeCell(
      t("applicantGroup"),
      makeElement("span", {
        className: "applicant-category",
        text: t("multipleApplicantGroups"),
      }),
    ),
    makeCell(
      t("opens"),
      earliestOpen
        ? makeTextStack(formatDate(earliestOpen), t("earliestOpening"))
        : makeElement("span", { text: "—" }),
    ),
    makeCell(
      t("deadline"),
      makeResponsiveDeadline(
        earliestOpen,
        nearestDeadline.closesAt,
        `${t("nextDeadlineLabel")} · ${deadlineNote(nearestDeadline, status)}`,
      ),
    ),
    makeCell(t("calendar"), makeElement("span", { text: "—" })),
    makeCell(t("favorite"), makeElement("span", { text: "—" })),
    makeCell(t("source"), source),
  );
  return row;
}

function markUniversityGroupChild(row, universityGroup) {
  if (!universityGroup) return;
  row.classList.add("university-group-child");
  row.dataset.universityGroup = universityGroup.universityId;
}

function appendWindowGroupRows(
  tbody,
  windowGroup,
  status,
  universityGroup = null,
) {
  const [representative, ...additionalRecords] = windowGroup.records;
  const representativeRow = createRow(representative, status, windowGroup);
  markUniversityGroupChild(representativeRow, universityGroup);
  tbody.appendChild(representativeRow);
  if (!state.expandedWindowGroups.has(windowGroup.key)) return;
  additionalRecords.forEach((record) => {
    const row = createRow(record, status);
    row.classList.add("window-group-child");
    markUniversityGroupChild(row, universityGroup);
    tbody.appendChild(row);
  });
}

function predictionConfidenceText(record) {
  const labels = {
    low: t("lowConfidence"),
    medium: t("mediumConfidence"),
    high: t("highConfidence"),
  };
  return `${labels[record.confidence] || t("estimate")} · ${record.evidenceCycleCount} ${t("historicalCycles")}`;
}

function createGroup(status, records) {
  const heading = statusLabels()[status];
  const { section, tbody } = createTableSection(
    status,
    heading,
    `${records.length} ${t("windows")}`,
    [
      { label: rankColumnLabel(), sort: "rank" },
      t("universityEntry"),
      t("programmeIntake"),
      t("applicantGroup"),
      { label: t("opens"), sort: "opens" },
      { label: t("deadline"), sort: "deadline" },
      t("addCalendar"),
      t("favorite"),
      t("dataSource"),
    ],
  );
  const universityGroups = groupWindowRecordsForDisplay(records, {
    keyPrefix: status,
  });
  const { items, start, end, total, page, totalPages } = paginate(
    status,
    universityGroups,
  );
  items.forEach((universityGroup) => {
    if (!universityGroup.collapsible) {
      appendWindowGroupRows(tbody, universityGroup.windowGroups[0], status);
      return;
    }
    tbody.appendChild(createUniversityGroupRow(universityGroup, status));
    if (!state.expandedUniversityGroups.has(universityGroup.key)) return;
    const childStart = tbody.children.length;
    universityGroup.windowGroups.forEach((windowGroup) => {
      appendWindowGroupRows(tbody, windowGroup, status, universityGroup);
    });
    const childRows = [...tbody.children].slice(childStart);
    childRows.at(0)?.classList.add("university-group-child--first");
    childRows.at(-1)?.classList.add("university-group-child--last");
  });
  section.appendChild(
    createPagination(status, { start, end, total, page, totalPages }),
  );
  return section;
}

function paginate(key, items) {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.min(Math.max(state.pages[key] || 1, 1), totalPages);
  state.pages[key] = page;
  const startIndex = (page - 1) * PAGE_SIZE;
  return {
    items: items.slice(startIndex, startIndex + PAGE_SIZE),
    start: total ? startIndex + 1 : 0,
    end: Math.min(startIndex + PAGE_SIZE, total),
    total,
    page,
    totalPages,
  };
}

function createPagination(key, pagination) {
  if (pagination.total <= PAGE_SIZE) return document.createDocumentFragment();
  const wrapper = makeElement("div", { className: "table-pagination" });
  const label = makeElement("span", {
    className: "pagination-summary",
    text: `${pagination.start}-${pagination.end} / ${pagination.total}`,
  });
  const previous = makeElement("button", {
    className: "pagination-button",
    text: "‹",
    title: t("paginationPrevious"),
  });
  const next = makeElement("button", {
    className: "pagination-button",
    text: "›",
    title: t("paginationNext"),
  });
  previous.type = "button";
  next.type = "button";
  previous.disabled = pagination.page <= 1;
  next.disabled = pagination.page >= pagination.totalPages;
  previous.addEventListener("click", () => {
    state.pages[key] = Math.max(1, pagination.page - 1);
    render();
  });
  next.addEventListener("click", () => {
    state.pages[key] = Math.min(pagination.totalPages, pagination.page + 1);
    render();
  });
  wrapper.append(label, previous, next);
  return wrapper;
}

function createTableSection(
  status,
  heading,
  countLabel,
  columns,
  tableClass = "",
) {
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
  columns.forEach((column) => {
    const th = document.createElement("th");
    if (typeof column === "object" && column.sort) {
      const button = makeElement("button", {
        className:
          `table-sort-button ${state.sort === column.sort ? "active" : ""}`.trim(),
      });
      button.type = "button";
      button.dataset.sort = column.sort;
      button.append(
        makeElement("span", { text: column.label }),
        makeElement("span", {
          className: "sort-indicator",
          text: state.sort === column.sort ? "↑" : "↕",
        }),
      );
      button.addEventListener("click", () => {
        state.sort = column.sort;
        resetPages();
        syncUrl();
        render();
      });
      th.appendChild(button);
    } else {
      th.textContent = typeof column === "object" ? column.label : column;
    }
    headRow.appendChild(th);
  });
  head.appendChild(headRow);
  const tbody = document.createElement("tbody");
  table.append(head, tbody);
  wrapper.appendChild(table);
  section.append(groupHeading, wrapper);
  return { section, tbody };
}

function directoryStatus(university) {
  if (university.rankingOnly) return [t("rankingOnly"), "homepage"];
  const status = university.admissionsDiscovery;
  if (status === "curated") return [t("curatedEntry"), "verified"];
  if (status === "discovered") return [t("discoveredEntry"), "discovered"];
  if (status === "low-confidence") return [t("candidateEntry"), "candidate"];
  return [t("homepageEntry"), "homepage"];
}

function monitorStatus(university) {
  if (university.rankingOnly) return [t("notMonitored"), "homepage"];
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
  if (university.rankingOnly) {
    return [t("rankingDataOnly"), t("notInQsMonitor")];
  }
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
  if (university.rankingOnly) {
    return [t("unverified"), t("rankingOnlyMasters")];
  }
  const availability = university.windowPolicy?.mastersAvailability;
  if (availability === "broad")
    return [t("broadMasters"), t("representativeAvailable")];
  if (availability === "limited") {
    return [t("limitedMasters"), t("someNotDirect")];
  }
  return [t("unverified"), t("inspectProgramme")];
}

function isExceptionUniversity(university) {
  // A blocked monitor request means the crawler was rejected, not that users
  // lack a usable official route. Keep those universities in the directory.
  return needsManualCheck(university);
}

function renderCoverage() {
  // Coverage remains available in data/coverage.json for development, but the
  // public page no longer exposes the internal build-progress panel.
}

function createUniversityGroup(universities, status = "unknown") {
  const heading = statusLabels()[status];
  const { section, tbody } = createTableSection(
    status,
    heading,
    `${universities.length} ${t("schools")}`,
    [
      { label: rankColumnLabel(), sort: "rank" },
      t("universityEntry"),
      t("mastersScope"),
      t("countries"),
      t("entryStatus"),
      t("latestCheck"),
      t("graduateApplication"),
      t("dateNotes"),
      t("schoolReviews"),
    ],
    "university-table",
  );
  const sortedUniversities = universities.sort(
    (a, b) =>
      a.rankPosition - b.rankPosition || a.school.localeCompare(b.school),
  );
  const { items, start, end, total, page, totalPages } = paginate(
    status,
    sortedUniversities,
  );
  items.forEach((university) => {
    const [statusLabel, statusClass] = directoryStatus(university);
    const [monitorLabel, monitorClass] = monitorStatus(university);
    const rankLabel = formatRank(university.rankDisplay);
    const directUrl = university.admissionsUrl;
    const directLabel = t("applicationEntry");
    const row = document.createElement("tr");
    row.className = "university-card-row";
    const schoolText = schoolLabels(university, state.language);
    const school = makeTextStack(schoolText.primary, schoolText.secondary);
    const admissions = university.rankingOnly
      ? makeLink(t("rankingSource"), university.rankingSourceUrl, "source-link")
      : directUrl
        ? makeLink(directLabel, directUrl, "school-link")
        : makeElement("span", {
            className: "school-meta",
            text: t("programmeDirectoryRequired"),
          });
    const actions = document.createDocumentFragment();
    actions.appendChild(admissions);
    if (!university.rankingOnly) {
      actions.appendChild(
        makeLink(t("officialWebsite"), university.homepageUrl, "source-link"),
      );
    }
    actions.appendChild(
      makeFavoriteButton(favoriteKey("university", university.id)),
    );
    const [policyPrimary, policySecondary] = policyDescription(university);
    const [mastersPrimary, mastersSecondary] =
      mastersAvailabilityDescription(university);
    row.append(
      makeCell(
        t("rank"),
        makeElement("span", { className: "rank-cell", text: rankLabel }),
      ),
      makeCell(t("universityEntry"), school),
      makeCell(
        t("mastersScope"),
        makeTextStack(mastersPrimary, mastersSecondary),
      ),
      makeCell(
        t("countries"),
        makeElement("span", {
          text: countryLabel(university.country, state.language),
        }),
      ),
      makeCell(
        t("entryStatus"),
        makeElement("span", {
          className: `source-badge ${statusClass}`,
          text: statusLabel,
        }),
      ),
      makeCell(
        t("latestCheck"),
        makeElement("span", {
          className: `source-badge ${monitorClass}`,
          text: monitorLabel,
        }),
      ),
      makeCell(t("graduateApplication"), actions),
      makeCell(
        t("dateNotes"),
        makeTextStack(policyPrimary, policySecondary, "date-primary"),
      ),
      makeCell(t("schoolReviews"), makeReviewButton(university)),
    );
    tbody.appendChild(row);
  });
  section.appendChild(
    createPagination(status, { start, end, total, page, totalPages }),
  );
  return section;
}

function renderCounts(records, universities) {
  const applicationCounts = countUniversitiesByStatus(records, getStatus);
  const allUniversityIds = new Set([
    ...records.map((record) => record.universityId).filter(Boolean),
    ...universities.map((university) => university.id).filter(Boolean),
  ]);
  const counts = {
    all: allUniversityIds.size,
    ...applicationCounts,
    exception: universities.filter(isExceptionUniversity).length,
    unknown: universities.length,
  };
  Object.entries(counts).forEach(([status, count]) => {
    const node = document.getElementById(`count-${status}`);
    if (node) node.textContent = count;
  });
  const mobileOpen = document.getElementById("mobile-open-count");
  const mobileUpcoming = document.getElementById("mobile-upcoming-count");
  const heroUpcoming = document.getElementById("hero-upcoming-count");
  const heroException = document.getElementById("hero-exception-count");
  if (mobileOpen) mobileOpen.textContent = counts.open;
  if (mobileUpcoming) mobileUpcoming.textContent = counts.upcoming;
  if (heroUpcoming) heroUpcoming.textContent = counts.upcoming;
  if (heroException) heroException.textContent = counts.exception;
  return counts;
}

function render() {
  const baseRecords = filteredRecords();
  const baseUniversities = filteredUniversities();
  const counts = renderCounts(baseRecords, baseUniversities);
  const records = recordsForCurrentView(baseRecords);
  const exceptionUniversities = baseUniversities.filter(isExceptionUniversity);
  const container = document.getElementById("application-groups");
  const emptyState = document.getElementById("empty-state");
  document.body.dataset.viewStatus = state.status;
  container.replaceChildren();

  ["open", "upcoming", "future", "closed"].forEach((status) => {
    if (!hasActiveSearch() && state.status !== status) return;
    const groupRecords = records
      .filter((record) => getStatus(record) === status)
      .sort(compareRecords);
    if (groupRecords.length) {
      container.appendChild(createGroup(status, groupRecords));
    }
  });
  if (state.status === "exception" && exceptionUniversities.length) {
    container.appendChild(
      createUniversityGroup([...exceptionUniversities], "exception"),
    );
  }
  if (
    (state.status === "unknown" || hasActiveSearch()) &&
    baseUniversities.length
  ) {
    container.appendChild(createUniversityGroup([...baseUniversities]));
  }

  emptyState.hidden =
    !activeNonStatusFilter() ||
    records.length > 0 ||
    (state.status === "exception" && exceptionUniversities.length > 0) ||
    ((state.status === "unknown" || hasActiveSearch()) &&
      baseUniversities.length > 0);
  document.getElementById("hero-open-count").textContent = counts.open;
  document.querySelectorAll("[data-mobile-sort]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mobileSort === state.sort);
  });
  updateResultsToolbar(records, baseUniversities, exceptionUniversities);
  updateStatusTabs();
  updateMobileFilterToggle();
  updateFavoriteControls();
}

function syncUrl() {
  const params = new URLSearchParams();
  if (state.search) params.set("q", state.search);
  if (state.ranking !== "qs") params.set("ranking", state.ranking);
  if (state.region !== "all") params.set("region", state.region);
  if (state.intake !== "all") params.set("intake", state.intake);
  if (state.status !== "open") params.set("status", state.status);
  if (state.sort !== "rank") params.set("sort", state.sort);
  if (state.rankLimit !== "200") params.set("rank", state.rankLimit);
  history.replaceState(
    null,
    "",
    `${location.pathname}${params.size ? `?${params}` : ""}${location.hash}`,
  );
}

function loadUrlState() {
  const params = new URLSearchParams(location.search);
  state.search = params.get("q") || "";
  state.ranking = params.get("ranking") || "qs";
  state.region = params.get("region") || "all";
  state.intake = params.get("intake") || "all";
  state.status = params.get("status") || "open";
  state.sort = ["rank", "opens", "deadline"].includes(params.get("sort"))
    ? params.get("sort")
    : "rank";
  state.rankLimit = ["30", "50", "100", "150", "200"].includes(
    params.get("rank"),
  )
    ? params.get("rank")
    : params.get("top") === "100"
      ? "100"
      : "200";
}

function updateFavoriteControls() {
  const count = state.favorites.size;
  document.getElementById("favorite-count").textContent = count;
  document
    .getElementById("favorites-toggle")
    .classList.toggle("active", state.favoritesOnly);
  document.getElementById("export-favorites").disabled = !state.data.some(
    (record) => state.favorites.has(favoriteKey("window", record.id)),
  );
  document
    .querySelectorAll(".favorite-button[data-favorite-key]")
    .forEach((button) => {
      const active = state.favorites.has(button.dataset.favoriteKey);
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      button.textContent = active ? t("favorited") : t("favorite");
      button.title = active ? t("removeFavorite") : t("favorite");
    });
}

function applyStaticTranslations() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const translated = t(node.dataset.i18n);
    if (translated !== node.dataset.i18n) node.textContent = translated;
  });
  document.querySelectorAll("[data-i18n-html]").forEach((node) => {
    const translated = t(node.dataset.i18nHtml);
    if (translated !== node.dataset.i18nHtml) node.innerHTML = translated;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const translated = t(node.dataset.i18nPlaceholder);
    if (translated !== node.dataset.i18nPlaceholder)
      node.placeholder = translated;
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    const translated = t(node.dataset.i18nAriaLabel);
    if (translated !== node.dataset.i18nAriaLabel) {
      node.setAttribute("aria-label", translated);
    }
  });
  document.getElementById("language-toggle").textContent =
    state.language === "en" ? "中文" : "EN";
  document.getElementById("theme-toggle").textContent =
    state.theme === "dark" ? "☀" : "☾";
  document
    .getElementById("theme-toggle")
    .setAttribute(
      "aria-label",
      state.theme === "dark" ? t("switchToLight") : t("switchToDark"),
    );
  updateRankRangeOptions();
  updateAuthUi();
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
    button.textContent = state.theme === "dark" ? "☀" : "☾";
    button.setAttribute(
      "aria-label",
      state.theme === "dark" ? t("switchToLight") : t("switchToDark"),
    );
  }
}

function loadTurnstile(siteKey) {
  if (!siteKey || document.querySelector("script[data-gradwindow-turnstile]")) {
    return;
  }
  const container = document.getElementById("turnstile-container");
  if (!container) return;
  const widget = makeElement("div", { className: "cf-turnstile" });
  widget.dataset.sitekey = siteKey;
  widget.dataset.action = "turnstile-spin-v1";
  widget.dataset.theme = state.theme === "dark" ? "dark" : "light";
  container.appendChild(widget);
  const script = document.createElement("script");
  script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js";
  script.async = true;
  script.defer = true;
  script.dataset.gradwindowTurnstile = "true";
  document.head.appendChild(script);
}

function setupSubscription() {
  const form = document.getElementById("subscribe-form");
  const button = document.getElementById("subscribe-button");
  const status = document.getElementById("subscribe-status");
  if (!form || !button || !status) return;
  const config = window.GRADWINDOW_CONFIG || {};
  const endpoint = String(config.subscribeUrl || "").replace(/\/$/, "");
  if (!endpoint) {
    button.disabled = true;
    status.textContent = t("subscribeUnavailable");
    return;
  }
  const subscriptionState = new URLSearchParams(window.location.search).get(
    "subscription",
  );
  if (subscriptionState === "confirmed") {
    status.className = "subscribe-status success";
    status.textContent = t("subscriptionConfirmed");
  } else if (subscriptionState === "invalid") {
    status.className = "subscribe-status error";
    status.textContent = t("subscriptionInvalid");
  }
  button.disabled = false;
  if (!subscriptionState) status.textContent = "";
  loadTurnstile(config.turnstileSiteKey || "");
  if (form.dataset.bound === "true") return;
  form.dataset.bound = "true";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("subscribe-email").value.trim();
    const turnstileToken =
      form.querySelector('[name="cf-turnstile-response"]')?.value || "";
    button.disabled = true;
    status.className = "subscribe-status";
    status.textContent = t("subscribeSending");
    try {
      const response = await fetch(`${endpoint}/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          language: state.language,
          consent: true,
          turnstileToken,
        }),
      });
      if (!response.ok) throw new Error("subscribe failed");
      form.reset();
      status.className = "subscribe-status success";
      status.textContent = t("subscribeSuccess");
      if (window.turnstile) window.turnstile.reset();
    } catch {
      status.className = "subscribe-status error";
      status.textContent = t("subscribeError");
    } finally {
      button.disabled = false;
    }
  });
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
  refreshFilterOptions();
  updateDataNotes();
  renderCoverage();
  setupHero();
  setupSubscription();
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
      state.language === "zh"
        ? "官方申请目录"
        : "Official admissions directory";
    const mobileLink = document.getElementById("mobile-deadline-link");
    if (mobileLink) mobileLink.removeAttribute("target");
    const mobileSchool = document.getElementById("mobile-deadline-school");
    const mobileDate = document.getElementById("mobile-deadline-date");
    const mobileNote = document.getElementById("mobile-deadline-note");
    if (mobileSchool)
      mobileSchool.textContent =
        state.language === "zh"
          ? "官方申请目录"
          : "Official admissions directory";
    if (mobileDate) mobileDate.textContent = "TOP 200";
    if (mobileNote) mobileNote.textContent = "";
    return;
  }
  const dateParts = deadlineDatePartsFormatter()
    .formatToParts(parseDate(futureDeadline.closesAt))
    .reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
  document.getElementById("hero-deadline-day").textContent = dateParts.day;
  document.getElementById("hero-deadline-month").textContent =
    dateParts.month.toUpperCase();
  document.getElementById("hero-deadline-school").textContent = schoolLabels(
    futureDeadline,
    state.language,
  ).primary;
  const mobileLink = document.getElementById("mobile-deadline-link");
  const mobileSchool = document.getElementById("mobile-deadline-school");
  const mobileDate = document.getElementById("mobile-deadline-date");
  const mobileNote = document.getElementById("mobile-deadline-note");
  if (mobileLink) {
    mobileLink.href =
      safeUrl(futureDeadline.applicationUrl) || "#application-groups";
    mobileLink.target = safeUrl(futureDeadline.applicationUrl) ? "_blank" : "";
    mobileLink.rel = "noreferrer";
  }
  if (mobileSchool)
    mobileSchool.textContent = schoolLabels(
      futureDeadline,
      state.language,
    ).primary;
  if (mobileDate) mobileDate.textContent = formatDate(futureDeadline.closesAt);
  if (mobileNote)
    mobileNote.textContent = deadlineNote(
      futureDeadline,
      getStatus(futureDeadline),
    );
}

function setMobileNavActive(name) {
  document.querySelectorAll("[data-mobile-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mobileNav === name);
  });
}

function updateMobileFilterToggle() {
  const toolbar = document.querySelector(".quick-filter-panel .toolbar");
  const button = document.getElementById("mobile-filter-toggle");
  const label = document.getElementById("mobile-filter-toggle-label");
  if (!toolbar || !button || !label) return;
  const expanded = toolbar.classList.contains("mobile-filters-open");
  const hasAdvancedFilters =
    state.ranking !== "qs" ||
    state.region !== "all" ||
    state.intake !== "all" ||
    state.rankLimit !== "200";
  button.setAttribute("aria-expanded", String(expanded));
  button.classList.toggle("active", expanded || hasAdvancedFilters);
  label.textContent = t(expanded ? "hideFilters" : "showFilters");
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
  document
    .getElementById("mobile-filter-toggle")
    .addEventListener("click", () => {
      document
        .querySelector(".quick-filter-panel .toolbar")
        .classList.toggle("mobile-filters-open");
      updateMobileFilterToggle();
    });
  document.getElementById("search-input").addEventListener("input", (event) => {
    state.search = event.target.value;
    setMobileNavActive("search");
    resetPages();
    syncUrl();
    render();
  });
  document
    .getElementById("ranking-filter")
    .addEventListener("change", (event) => {
      state.ranking = event.target.value;
      state.region = "all";
      state.intake = "all";
      if (state.ranking !== "qs") state.sort = "rank";
      resetPages();
      refreshFilterOptions();
      updateRankRangeOptions();
      syncUrl();
      updateStatusTabs();
      render();
    });
  document
    .getElementById("region-filter")
    .addEventListener("change", (event) => {
      state.region = event.target.value;
      resetPages();
      syncUrl();
      render();
    });
  document
    .getElementById("intake-filter")
    .addEventListener("change", (event) => {
      state.intake = event.target.value;
      resetPages();
      syncUrl();
      render();
    });
  document
    .getElementById("rank-range-filter")
    .addEventListener("change", (event) => {
      state.rankLimit = event.target.value;
      resetPages();
      syncUrl();
      render();
    });
  document.querySelectorAll(".status-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.status = button.dataset.status;
      resetPages();
      syncUrl();
      updateStatusTabs();
      render();
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        return;
      }
      event.preventDefault();
      const tabs = [...document.querySelectorAll(".status-tab")];
      const currentIndex = tabs.indexOf(button);
      const nextIndex =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? tabs.length - 1
            : (currentIndex +
                (event.key === "ArrowRight" ? 1 : -1) +
                tabs.length) %
              tabs.length;
      state.status = tabs[nextIndex].dataset.status;
      resetPages();
      syncUrl();
      render();
      updateStatusTabs(state.status);
    });
  });
  document
    .getElementById("expand-visible-groups")
    .addEventListener("click", () => setVisibleUniversityGroups(true));
  document
    .getElementById("collapse-visible-groups")
    .addEventListener("click", () => setVisibleUniversityGroups(false));
  document.getElementById("favorites-toggle").addEventListener("click", () => {
    state.favoritesOnly = !state.favoritesOnly;
    resetPages();
    render();
  });
  document
    .getElementById("export-favorites")
    .addEventListener("click", downloadFavoriteCalendars);

  document.querySelectorAll("[data-mobile-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      state.sort = button.dataset.mobileSort;
      resetPages();
      syncUrl();
      render();
    });
  });

  document.querySelectorAll("[data-mobile-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      const destination = button.dataset.mobileNav;
      setMobileNavActive(destination);
      if (destination === "home") {
        state.search = "";
        state.favoritesOnly = false;
        state.status = "open";
        document.getElementById("search-input").value = "";
        updateStatusTabs();
        resetPages();
        syncUrl();
        render();
        document
          .getElementById("application-board")
          .scrollIntoView({ behavior: "smooth" });
      } else if (destination === "search") {
        document
          .getElementById("application-board")
          .scrollIntoView({ behavior: "smooth" });
        setTimeout(() => document.getElementById("search-input")?.focus(), 250);
      } else if (destination === "favorites") {
        state.favoritesOnly = true;
        resetPages();
        syncUrl();
        render();
        document
          .getElementById("application-groups")
          .scrollIntoView({ behavior: "smooth" });
      } else if (destination === "profile") {
        openAuthPanel();
      }
    });
  });
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
      rankingsPayload,
      programmeTranslationsPayload,
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
      fetchOptionalJson("./data/global-rankings.json", { rankings: {} }),
      fetchOptionalJson("./data/programme-translations.json", {
        translations: {},
      }),
    ]);
    setProgrammeTranslations(programmeTranslationsPayload);
    state.coverage = coveragePayload;
    state.monitorPayload = monitorPayload;
    state.optionalFailureCount = optionalFailures.length;
    state.sourceMonitor = sourceMonitorPayload.applications || {};
    state.universities = universityPayload.universities;
    state.universityById = new Map(
      state.universities.map((university) => [university.id, university]),
    );
    state.rankingPayload = rankingsPayload;
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
    const universityById = state.universityById;
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
        schoolAliasesZh:
          university.schoolAliasesZh || record.schoolAliasesZh || [],
        qsRank: university.qsRank || record.qsRank || 999,
        country: university.country || record.country || "",
        region: university.region || record.region || "",
        program:
          program.name ||
          programmeGroup.name ||
          record.program ||
          (record.scopeType === "institution"
            ? t("institutionWindow")
            : record.scopeId),
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
    if (selectedRankingDefinition().available === false) state.ranking = "qs";
    updateRankingAvailability();

    refreshFilterOptions();
    const legacyIntake = state.intake;
    const matchingLegacyRecord = state.data.find(
      (record) => record.intake === legacyIntake,
    );
    if (matchingLegacyRecord) {
      state.intake = recordIntake(matchingLegacyRecord).key;
    }
    populateIntakeSelect();
    const allowedStatuses = new Set([
      "open",
      "upcoming",
      "future",
      "closed",
      "exception",
      "unknown",
    ]);
    if (!allowedStatuses.has(state.status)) state.status = "open";
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
    document.getElementById("ranking-filter").value = state.ranking;
    updateRankRangeOptions();
    updateStatusTabs();
    const schoolCount = state.universities.length;
    document.getElementById("total-schools").textContent = schoolCount;
    document.getElementById("total-records").textContent = state.officialCount;
    document.getElementById("total-predictions").textContent =
      state.predictionCount;
    updateDataNotes();
    document.getElementById("demo-banner").hidden = false;
    renderCoverage();
    setupHero();
    setupSubscription();
    bindEvents();
    initAuth({ render, updateFavoriteControls, updateReviewAuthState });
    setupAuthPanel();
    setupReviewPanel();
    setupWindowDetailPanel();
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
