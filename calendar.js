import { I18N } from "./i18n.js";
import { getApplicationStatus } from "./status.js";
import { canonicalIntake, intakeLabel } from "./intake-filter.js";
import { countryLabel, programmeLabel, roundLabel, schoolLabels } from "./localization.js";

const state = {
  records: [],
  search: "",
  qsLimit: 200,
  status: "all",
  month: null,
  language: "en",
  theme: "light",
};

function t(key) {
  return I18N[state.language][key] || I18N.en[key] || key;
}

function todayUtc() {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}

function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

function monthStart(date = todayUtc()) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function addMonths(date, offset) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + offset, 1));
}

function formatDate(value) {
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : "en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(parseDate(value));
}

function formatMonth(value) {
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : "en-GB", {
    year: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(value);
}

function weekdayFormatter() {
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : "en-GB", {
    weekday: "short",
    timeZone: "UTC",
  });
}

function acronym(value = "") {
  return String(value)
    .split(/[^A-Za-z0-9]+/)
    .filter((word) => word && !["of", "the", "and"].includes(word.toLowerCase()))
    .map((word) => word[0])
    .join("")
    .toLocaleLowerCase("zh-CN");
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

function makeLink(text, url, className = "") {
  const validUrl = safeUrl(url);
  if (!validUrl) return makeElement("span", { className, text });
  const link = makeElement("a", { className, text });
  link.href = validUrl;
  link.target = "_blank";
  link.rel = "noreferrer";
  return link;
}

function calendarEvents(records) {
  return records.flatMap((record) => [
    { type: "open", date: record.opensAt, record },
    { type: "deadline", date: record.closesAt, record },
  ]);
}

function filteredRecords() {
  const query = state.search.trim().toLocaleLowerCase("zh-CN");
  return state.records.filter((record) => {
    const searchable = [
      record.school,
      record.schoolZh,
      acronym(record.school),
      record.program,
      record.universityId,
      record.scopeId,
      record.country,
      record.region,
    ]
      .join(" ")
      .toLocaleLowerCase("zh-CN");
    return (
      record.qsRank <= state.qsLimit &&
      (state.status === "all" || getApplicationStatus(record) === state.status) &&
      (!query || searchable.includes(query))
    );
  });
}

function ensureCalendarMonth(records) {
  if (state.month) return;
  const nextEvent = calendarEvents(records)
    .filter((event) => parseDate(event.date) >= todayUtc())
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  state.month = nextEvent ? monthStart(parseDate(nextEvent.date)) : monthStart();
}

function eventLabel(event) {
  const school = schoolLabels(event.record, state.language).primary;
  return `${event.type === "open" ? t("calendarEventOpen") : t("calendarEventDeadline")} · ${school}`;
}

function makeCalendarEvent(event) {
  const link = makeLink(eventLabel(event), event.record.applicationUrl, `calendar-event ${event.type}`);
  link.title = [
    schoolLabels(event.record, state.language).primary,
    programmeLabel(event.record.scopeId, event.record.program, state.language),
  ].join(" · ");
  return link;
}

function renderCalendar(records) {
  ensureCalendarMonth(records);
  document.getElementById("calendar-month-label").textContent = formatMonth(state.month);

  const weekdays = document.getElementById("calendar-weekdays");
  const formatter = weekdayFormatter();
  const weekStart = new Date(Date.UTC(2026, 5, 15));
  weekdays.replaceChildren(
    ...Array.from({ length: 7 }, (_, index) =>
      makeElement("span", {
        text: formatter.format(new Date(weekStart.getTime() + index * 86_400_000)),
      }),
    ),
  );

  const monthIndex = state.month.getUTCMonth();
  const firstOffset = (state.month.getUTCDay() + 6) % 7;
  const firstCell = new Date(Date.UTC(state.month.getUTCFullYear(), monthIndex, 1 - firstOffset));
  const eventsByDate = new Map();
  calendarEvents(records).forEach((event) => {
    if (monthStart(parseDate(event.date)).getTime() !== state.month.getTime()) return;
    const events = eventsByDate.get(event.date) || [];
    events.push(event);
    eventsByDate.set(event.date, events);
  });

  const todayKey = todayUtc().toISOString().slice(0, 10);
  const cells = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(firstCell.getTime() + index * 86_400_000);
    const key = date.toISOString().slice(0, 10);
    const cell = makeElement("div", {
      className: `calendar-cell${date.getUTCMonth() === monthIndex ? "" : " muted"}${key === todayKey ? " today" : ""}`,
    });
    cell.appendChild(makeElement("span", { className: "calendar-day", text: date.getUTCDate() }));
    const events = (eventsByDate.get(key) || []).sort((a, b) => {
      if (a.type !== b.type) return a.type === "deadline" ? -1 : 1;
      return a.record.qsRank - b.record.qsRank;
    });
    events.slice(0, 4).forEach((event) => cell.appendChild(makeCalendarEvent(event)));
    if (events.length > 4) {
      cell.appendChild(makeElement("span", { className: "calendar-more", text: `+${events.length - 4} ${t("calendarMore")}` }));
    }
    return cell;
  });
  document.getElementById("calendar-grid").replaceChildren(...cells);
}

function renderList(records) {
  const events = calendarEvents(records)
    .filter((event) => monthStart(parseDate(event.date)).getTime() === state.month.getTime())
    .sort((a, b) => a.date.localeCompare(b.date) || a.record.qsRank - b.record.qsRank);
  document.getElementById("calendar-result-count").textContent =
    `${events.length} ${state.language === "zh" ? "个事件" : "events"}`;
  const list = document.getElementById("calendar-list");
  if (!events.length) {
    list.replaceChildren(makeElement("div", { className: "empty-state compact", text: t("calendarNoEvents") }));
    return;
  }
  list.replaceChildren(
    ...events.map((event) => {
      const card = makeElement("article", { className: `calendar-list-item ${event.type}` });
      const school = schoolLabels(event.record, state.language);
      const intake = intakeLabel(canonicalIntake(event.record), state.language);
      const round = roundLabel(event.record.round, state.language);
      card.append(
        makeElement("span", { className: "date-secondary", text: `${formatDate(event.date)} · QS #${event.record.qsRank}` }),
        makeLink(eventLabel(event), event.record.applicationUrl, "school-link"),
        makeElement("span", {
          className: "school-meta",
          text: [
            programmeLabel(event.record.scopeId, event.record.program, state.language),
            intake,
            round,
            countryLabel(event.record.country, state.language),
            school.secondary,
          ].filter(Boolean).join(" · "),
        }),
      );
      return card;
    }),
  );
}

function render() {
  const records = filteredRecords();
  ensureCalendarMonth(records);
  renderCalendar(records);
  renderList(records);
}

function applyStaticTranslations() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  document.getElementById("language-toggle").textContent =
    state.language === "en" ? "中文" : "EN";
  document.getElementById("theme-toggle").textContent =
    state.theme === "dark" ? "☀" : "☾";
  document.title =
    state.language === "zh"
      ? "GradWindow · 申请日历"
      : "GradWindow · Application Calendar";
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  localStorage.setItem("gradwindow:theme", state.theme);
  const button = document.getElementById("theme-toggle");
  if (button) button.textContent = state.theme === "dark" ? "☀" : "☾";
}

function bindEvents() {
  document.getElementById("language-toggle").addEventListener("click", () => {
    state.language = state.language === "en" ? "zh" : "en";
    localStorage.setItem("gradwindow:language", state.language);
    applyStaticTranslations();
    render();
  });
  document.getElementById("theme-toggle").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme();
  });
  document.getElementById("calendar-search").addEventListener("input", (event) => {
    state.search = event.target.value;
    state.month = null;
    render();
  });
  document.getElementById("calendar-qs").addEventListener("change", (event) => {
    state.qsLimit = Number(event.target.value);
    state.month = null;
    render();
  });
  document.getElementById("calendar-status").addEventListener("change", (event) => {
    state.status = event.target.value;
    state.month = null;
    render();
  });
  document.getElementById("calendar-prev").addEventListener("click", () => {
    state.month = addMonths(state.month || monthStart(), -1);
    render();
  });
  document.getElementById("calendar-next").addEventListener("click", () => {
    state.month = addMonths(state.month || monthStart(), 1);
    render();
  });
  document.getElementById("calendar-today").addEventListener("click", () => {
    state.month = monthStart();
    render();
  });
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function init() {
  state.language = localStorage.getItem("gradwindow:language") === "zh" ? "zh" : "en";
  const savedTheme = localStorage.getItem("gradwindow:theme");
  state.theme = ["light", "dark"].includes(savedTheme)
    ? savedTheme
    : window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  applyTheme();
  applyStaticTranslations();

  const [applications, predictions, universities, programs, groups] = await Promise.all([
    fetchJson("./data/applications.json"),
    fetchJson("./data/predictions.json"),
    fetchJson("./data/universities.json"),
    fetchJson("./data/programs.json"),
    fetchJson("./data/programme-groups.json"),
  ]);
  const universityById = new Map(universities.universities.map((item) => [item.id, item]));
  const programById = new Map(programs.programs.map((item) => [item.id, item]));
  const groupById = new Map(groups.groups.map((item) => [item.id, item]));
  const enrich = (record, dataStatus) => {
    const university = universityById.get(record.universityId) || {};
    const program =
      record.scopeType === "programme" ? programById.get(record.scopeId) || {} : {};
    const group =
      record.scopeType === "programme-group" ? groupById.get(record.scopeId) || {} : {};
    return {
      ...record,
      dataStatus,
      school: university.school || record.school || "",
      schoolZh: university.schoolZh || record.schoolZh || "",
      qsRank: university.qsRank || record.qsRank || 999,
      country: university.country || record.country || "",
      region: university.region || record.region || "",
      program:
        program.name ||
        group.name ||
        record.program ||
        record.scopeId,
    };
  };
  state.records = [
    ...applications.applications.map((record) => enrich(record, "official")),
    ...predictions.predictions.map((record) => enrich(record, "predicted")),
  ];
  bindEvents();
  render();
}

init().catch((error) => {
  document.getElementById("calendar-grid").replaceChildren(
    makeElement("div", { className: "empty-state", text: t("loadFailed") }),
  );
  console.error(error);
});
