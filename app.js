import { I18N } from "./i18n.js?v=20260626-calendar-menu";
import { getApplicationStatus } from "./status.js";
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

const PAGE_SIZE = 20;
const VISITOR_KEY = "gradwindow:visitor";
const AUTH_TOKEN_KEY = "gradwindow:authToken";

const state = {
  data: [],
  universities: [],
  programs: [],
  programmeGroups: [],
  applicantCategoryLabels: {},
  policies: [],
  coverage: null,
  sourceMonitor: {},
  rankingPayload: { rankings: {} },
  universityById: new Map(),
  ranking: "qs",
  officialCount: 0,
  predictionCount: 0,
  meta: {},
  search: "",
  region: "all",
  intake: "all",
  status: "open",
  sort: "rank",
  rankLimit: "200",
  favorites: new Set(),
  favoritesOnly: false,
  language: "en",
  theme: "light",
  monitorPayload: null,
  optionalFailureCount: 0,
  pages: {},
  activeReviewUniversity: null,
  authToken: "",
  user: null,
  favoriteSyncTimer: null,
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
    exception: { title: t("exceptionTitle"), description: t("exceptionDescription") },
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

function visitorId() {
  let value = localStorage.getItem(VISITOR_KEY);
  if (!value) {
    value = crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${crypto.getRandomValues(new Uint32Array(1))[0]}`;
    localStorage.setItem(VISITOR_KEY, value);
  }
  return value;
}

function feedbackApiBase() {
  const config = window.GRADWINDOW_CONFIG || {};
  return String(config.roadmapUrl || config.subscribeUrl || "").replace(/\/$/, "");
}

function authApiBase() {
  return feedbackApiBase();
}

function authHeaders(includeJson = true) {
  const headers = {};
  if (includeJson) headers["Content-Type"] = "application/json";
  if (state.authToken) headers.Authorization = `Bearer ${state.authToken}`;
  return headers;
}

function setAuthStatus(message, kind = "") {
  const status = document.getElementById("auth-status");
  if (!status) return;
  status.textContent = message || "";
  status.className = `auth-status${kind ? ` ${kind}` : ""}`;
}

function saveAuthToken(token) {
  state.authToken = token || "";
  if (state.authToken) localStorage.setItem(AUTH_TOKEN_KEY, state.authToken);
  else localStorage.removeItem(AUTH_TOKEN_KEY);
}

function acronym(value = "") {
  return String(value)
    .split(/[^A-Za-z0-9]+/)
    .filter((word) => word && !["of", "the", "and"].includes(word.toLowerCase()))
    .map((word) => word[0])
    .join("")
    .toLocaleLowerCase("zh-CN");
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

function resetPages() {
  state.pages = {};
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

function makeLinkedTextStack(primary, url, secondary, primaryClass = "date-primary") {
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
  localStorage.setItem("gradwindow:favorites", JSON.stringify([...state.favorites]));
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

function updateAuthUi() {
  const signedIn = Boolean(state.user);
  const toggle = document.getElementById("auth-toggle");
  if (toggle) {
    toggle.textContent = signedIn
      ? state.user.displayName || t("accountTitle")
      : t("signIn");
  }
  const signedOut = document.getElementById("auth-signed-out");
  const signedInPanel = document.getElementById("auth-signed-in");
  if (signedOut) signedOut.hidden = signedIn;
  if (signedInPanel) signedInPanel.hidden = !signedIn;
  if (signedIn) {
    document.getElementById("auth-user-name").textContent =
      state.user.displayName || t("accountTitle");
    document.getElementById("profile-name").value = state.user.displayName || "";
    document.getElementById("profile-country").value = state.user.country || "";
    document.getElementById("profile-intake").value = state.user.targetIntake || "";
  }
  updateReviewAuthState();
}

function openAuthPanel(message = "") {
  const panel = document.getElementById("auth-panel");
  if (!panel) return;
  panel.hidden = false;
  setAuthStatus(message);
  updateAuthUi();
  const email = document.getElementById("auth-email");
  const profileName = document.getElementById("profile-name");
  requestAnimationFrame(() => {
    if (state.user) profileName?.focus();
    else email?.focus();
  });
}

function closeAuthPanel() {
  const panel = document.getElementById("auth-panel");
  if (panel) panel.hidden = true;
}

async function refreshMe() {
  if (!state.authToken) return;
  const base = authApiBase();
  if (!base) return;
  try {
    const response = await fetch(`${base}/me`, {
      headers: authHeaders(false),
    });
    if (!response.ok) throw new Error("auth expired");
    const payload = await response.json();
    state.user = payload.user || null;
    const merged = new Set([
      ...state.favorites,
      ...((payload.favorites || []).filter(Boolean)),
    ]);
    state.favorites = merged;
    localStorage.setItem("gradwindow:favorites", JSON.stringify([...merged]));
    scheduleFavoriteSync();
  } catch {
    state.user = null;
    saveAuthToken("");
  }
  updateAuthUi();
  updateFavoriteControls();
  render();
}

function scheduleFavoriteSync() {
  if (!state.authToken || !state.user) return;
  clearTimeout(state.favoriteSyncTimer);
  state.favoriteSyncTimer = setTimeout(syncFavorites, 400);
}

async function syncFavorites() {
  if (!state.authToken || !state.user) return;
  const base = authApiBase();
  if (!base) return;
  try {
    await fetch(`${base}/me/favorites`, {
      method: "PUT",
      headers: authHeaders(),
      body: JSON.stringify({ favorites: [...state.favorites] }),
    });
  } catch {
    // Keep local favourites; the next change or login refresh will retry.
  }
}

async function requestLoginCode(email) {
  const base = authApiBase();
  if (!base) throw new Error("auth unavailable");
  setAuthStatus(t("authSendingCode"));
  const response = await fetch(`${base}/auth/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, language: state.language }),
  });
  if (!response.ok) throw new Error("login request failed");
  setAuthStatus(t("authCodeSent"), "success");
}

async function verifyLoginCode(email, code) {
  const base = authApiBase();
  if (!base) throw new Error("auth unavailable");
  setAuthStatus(t("authVerifying"));
  const response = await fetch(`${base}/auth/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });
  if (!response.ok) throw new Error("login verify failed");
  const payload = await response.json();
  saveAuthToken(payload.token || "");
  state.user = payload.user || null;
  state.favorites = new Set([
    ...state.favorites,
    ...((payload.favorites || []).filter(Boolean)),
  ]);
  localStorage.setItem("gradwindow:favorites", JSON.stringify([...state.favorites]));
  setAuthStatus(t("authSignedIn"), "success");
  updateAuthUi();
  updateFavoriteControls();
  render();
  scheduleFavoriteSync();
}

async function saveProfile() {
  const base = authApiBase();
  if (!base || !state.authToken) throw new Error("auth unavailable");
  const response = await fetch(`${base}/me`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify({
      displayName: document.getElementById("profile-name").value,
      country: document.getElementById("profile-country").value,
      targetIntake: document.getElementById("profile-intake").value,
      language: state.language,
    }),
  });
  if (!response.ok) throw new Error("profile failed");
  const payload = await response.json();
  state.user = payload.user || state.user;
  setAuthStatus(t("authProfileSaved"), "success");
  updateAuthUi();
}

async function signOut() {
  const base = authApiBase();
  if (base && state.authToken) {
    try {
      await fetch(`${base}/auth/logout`, {
        method: "POST",
        headers: authHeaders(false),
      });
    } catch {
      // Local sign-out still clears the session from this browser.
    }
  }
  state.user = null;
  saveAuthToken("");
  setAuthStatus("");
  updateAuthUi();
}

function makeReviewButton(university) {
  const button = makeElement("button", {
    className: "icon-button review-button",
    text: t("schoolReviews"),
    title: t("openSchoolReviews"),
  });
  button.type = "button";
  button.addEventListener("click", () => openUniversityReviews(university));
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

function outlookCalendarUrl(record) {
  const start = `${record.closesAt}T00:00:00Z`;
  const endDate = parseDate(record.closesAt);
  endDate.setUTCDate(endDate.getUTCDate() + 1);
  const end = `${endDate.toISOString().slice(0, 10)}T00:00:00Z`;
  const prefix = record.dataStatus === "predicted" ? "[ESTIMATE] " : "";
  const title = `${prefix}${record.school} ${record.program} application deadline`;
  const body = [
    record.dataStatus === "predicted"
      ? "Unofficial calendar-date estimate. Confirm on the official website before applying."
      : "",
    `Application: ${record.applicationUrl}`,
    `Source: ${record.sourceUrl}`,
  ].filter(Boolean).join("\n");
  const params = new URLSearchParams({
    path: "/calendar/action/compose",
    rru: "addevent",
    startdt: start,
    enddt: end,
    subject: title,
    body,
    allday: "true",
  });
  return `https://outlook.live.com/calendar/0/deeplink/compose?${params.toString()}`;
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

function makeCalendarMenu(record) {
  const menu = makeElement("details", { className: "calendar-menu" });
  const summary = makeElement("summary", {
    className: "calendar-menu-trigger",
    title: t("calendarOptions"),
  });
  summary.append(
    makeElement("span", { className: "calendar-menu-icon" }),
    makeElement("span", { className: "calendar-menu-label", text: t("addCalendar") }),
  );
  const options = makeElement("div", { className: "calendar-menu-options" });
  const makeDownloadOption = (label) => {
    const button = makeElement("button", {
      className: "calendar-menu-item",
      text: label,
      title: t("downloadIcs"),
    });
    button.type = "button";
    button.addEventListener("click", () => {
      downloadIcs(record);
      menu.open = false;
    });
    return button;
  };
  const apple = makeDownloadOption(t("appleCalendar"));
  const android = makeDownloadOption(t("androidCalendar"));
  const ics = makeElement("button", {
    className: "calendar-menu-item",
    text: t("downloadIcs"),
    title: t("downloadIcs"),
  });
  ics.type = "button";
  ics.addEventListener("click", () => {
    downloadIcs(record);
    menu.open = false;
  });
  options.append(
    makeLink(t("googleCalendar"), googleCalendarUrl(record), "calendar-menu-item"),
    makeLink(t("outlookCalendar"), outlookCalendarUrl(record), "calendar-menu-item"),
    apple,
    android,
    ics,
  );
  menu.append(summary, options);
  return menu;
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
  const intake = intakeLabel(canonicalIntake(record), state.language);
  const localizedRound = roundLabel(record.round, state.language);
  const programmeName = programmeLabel(
    record.scopeId,
    record.program,
    state.language,
  );
  const [sourceStatus, sourceClass] = record.dataStatus === "predicted"
    ? [t("estimateBadge"), "predicted"]
    : sourceMonitorDescription(record);

  const heading = makeElement("section", { className: "window-detail-heading" });
  const schoolRow = makeElement("div", { className: "window-detail-school-row" });
  schoolRow.append(
    makeElement("h2", { text: schoolText.primary }),
    makeElement("span", {
      className: "rank-cell",
      text: formatRank(
        selectedRankForUniversity(record.universityId)?.rankDisplay || record.qsRank,
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
    makeLink(programmeName, record.applicationUrl, "program-link window-detail-programme"),
  );

  const deadline = makeElement("section", { className: "window-detail-deadline" });
  deadline.append(
    makeElement("span", { text: t("deadline") }),
    makeElement("strong", { text: formatDate(record.closesAt) }),
    makeElement("small", { text: deadlineNote(record, status) }),
  );

  const info = makeElement("section", { className: "window-detail-section" });
  info.append(
    makeElement("h3", { text: t("mobileWindowDetails") }),
    detailField(t("opens"), formatDate(record.opensAt)),
    detailField(t("programmeIntake"), `${intake}${localizedRound ? ` · ${localizedRound}` : ""}`),
    detailField(t("applicantGroup"), applicantCategoryText(record.applicantCategories)),
    detailField(t("statusTabsLabel"), statusLabels()[status]?.title || status),
  );

  const source = makeElement("section", { className: "window-detail-section window-detail-source" });
  const sourceHeader = makeElement("div", { className: "window-detail-source-header" });
  sourceHeader.append(
    makeElement("h3", { text: t("dataSource") }),
    makeElement("span", { className: `source-badge ${sourceClass}`, text: sourceStatus }),
  );
  source.append(
    sourceHeader,
    makeElement("p", {
      text: record.dataStatus === "predicted"
        ? `${t("reference")} ${record.sourceCycle} · ${predictionConfidenceText(record)}`
        : `${t("verifiedOn")} ${record.verifiedAt}`,
    }),
    makeLink(
      record.dataStatus === "predicted" ? t("viewReference") : t("viewOfficial"),
      record.sourceUrl,
      "primary-button window-detail-source-link",
    ),
  );

  if (university) {
    const reviews = makeElement("section", { className: "window-detail-section window-detail-reviews" });
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
    const intake = canonicalIntake(record);
    if (intake.term === "academic") return;
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

function selectedRankingDefinition() {
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

function selectedRankingRows() {
  const ranking = selectedRankingDefinition();
  return ranking.available === false ? [] : ranking.rows || [];
}

function selectedRankByUniversityId() {
  return new Map(
    selectedRankingRows()
      .filter((row) => row.universityId)
      .map((row) => [row.universityId, row]),
  );
}

function selectedRankForUniversity(universityId) {
  return selectedRankByUniversityId().get(universityId) || null;
}

function recordsInSelectedRanking() {
  if (state.ranking !== "qs") return [];
  const rankedUniversityIds = new Set(
    selectedRankingRows()
      .map((row) => row.universityId)
      .filter(Boolean),
  );
  return state.data.filter((record) => rankedUniversityIds.has(record.universityId));
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
  return t("rankRangeTop").replace("{ranking}", rankingShortLabel()).replace("{limit}", limit);
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
    option.disabled = !ranking || ranking.available === false || !ranking.rows?.length;
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

function filteredRecords() {
  const query = state.search.trim().toLocaleLowerCase("zh-CN");
  return recordsInSelectedRanking().filter((record) => {
    const searchable = [
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
      .toLocaleLowerCase("zh-CN");

    return (
      (!query || searchable.includes(query)) &&
      (state.region === "all" || record.region === state.region) &&
      (state.intake === "all" ||
        canonicalIntake(record).key === state.intake) &&
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

function recordsForCurrentView(baseRecords) {
  if (hasActiveSearch()) return baseRecords;
  return baseRecords.filter((record) => getStatus(record) === state.status);
}

function createRow(record, status) {
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
      selectedRankForUniversity(record.universityId)?.rankDisplay || record.qsRank,
    ),
  });
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
  const programme = makeLinkedTextStack(
    programmeLabel(record.scopeId, record.program, state.language),
    record.applicationUrl,
    `${intake}${localizedRound ? ` · ${localizedRound}` : ""}`,
    "program-link date-primary",
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
  const { items, start, end, total, page, totalPages } = paginate(status, records);
  items.forEach((record) => tbody.appendChild(createRow(record, status)));
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
  columns.forEach((column) => {
    const th = document.createElement("th");
    if (typeof column === "object" && column.sort) {
      const button = makeElement("button", {
        className: `table-sort-button ${state.sort === column.sort ? "active" : ""}`.trim(),
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
  if (availability === "broad") return [t("broadMasters"), t("representativeAvailable")];
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
    (a, b) => a.rankPosition - b.rankPosition || a.school.localeCompare(b.school),
  );
  const { items, start, end, total, page, totalPages } = paginate(
    status,
    sortedUniversities,
  );
  items
    .forEach((university) => {
      const [statusLabel, statusClass] = directoryStatus(university);
      const [monitorLabel, monitorClass] = monitorStatus(university);
      const rankLabel = formatRank(university.rankDisplay);
      const directUrl = university.admissionsUrl;
      const directLabel = t("applicationEntry");
      const row = document.createElement("tr");
      const schoolText = schoolLabels(university, state.language);
      const school = makeTextStack(
        schoolText.primary,
        schoolText.secondary,
      );
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
        makeCell(t("rank"), makeElement("span", { className: "rank-cell", text: rankLabel })),
        makeCell(t("universityEntry"), school),
        makeCell(t("mastersScope"), makeTextStack(mastersPrimary, mastersSecondary)),
        makeCell(
          t("countries"),
          makeElement("span", {
            text: countryLabel(university.country, state.language),
          }),
        ),
        makeCell(t("entryStatus"), makeElement("span", { className: `source-badge ${statusClass}`, text: statusLabel })),
        makeCell(t("latestCheck"), makeElement("span", { className: `source-badge ${monitorClass}`, text: monitorLabel })),
        makeCell(t("graduateApplication"), actions),
        makeCell(t("dateNotes"), makeTextStack(policyPrimary, policySecondary, "date-primary")),
        makeCell(t("schoolReviews"), makeReviewButton(university)),
      );
      tbody.appendChild(row);
    });
  section.appendChild(
    createPagination(status, { start, end, total, page, totalPages }),
  );
  return section;
}

function commentDateFormatter() {
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : "en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function commentsEndpoint(universityId) {
  const base = feedbackApiBase();
  return base
    ? `${base}/universities/${encodeURIComponent(universityId)}/comments`
    : "";
}

function setReviewStatus(messageKey, tone = "") {
  const status = document.getElementById("review-status");
  if (!status) return;
  status.className = `review-status ${tone}`;
  status.textContent = messageKey ? t(messageKey) : "";
}

function renderComments(comments) {
  const list = document.getElementById("review-list");
  list.replaceChildren();
  if (!comments.length) {
    list.appendChild(
      makeElement("p", { className: "review-empty", text: t("reviewNoComments") }),
    );
    return;
  }
  comments.forEach((comment) => {
    const item = makeElement("article", { className: "review-item" });
    const avatar = makeElement("span", {
      className: `review-avatar ${comment.anonymous ? "cat-avatar" : "user-avatar"}`,
      text: comment.anonymous ? "" : acronym(comment.author || "G").slice(0, 2) || "G",
    });
    const meta = makeElement("div", { className: "review-item-meta" });
    meta.append(
      makeElement("strong", { text: comment.author || t("reviewAnonymous") }),
      makeElement("span", {
        text: comment.createdAt
          ? commentDateFormatter().format(new Date(comment.createdAt))
          : "",
      }),
    );
    item.append(
      avatar,
      makeElement("div", {
        className: "review-item-content",
      }),
    );
    item.querySelector(".review-item-content").append(
      meta,
      makeElement("p", { className: "review-item-body", text: comment.body || "" }),
    );
    list.appendChild(item);
  });
}

async function loadUniversityComments(universityId) {
  const endpoint = commentsEndpoint(universityId);
  if (!endpoint) {
    renderComments([]);
    setReviewStatus("reviewUnavailable", "error");
    return;
  }
  setReviewStatus("reviewLoading");
  try {
    const response = await fetch(endpoint, {
      headers: { "X-GradWindow-Visitor": visitorId() },
    });
    if (!response.ok) throw new Error("comments unavailable");
    const payload = await response.json();
    renderComments(payload.comments || []);
    setReviewStatus("");
  } catch {
    renderComments([]);
    setReviewStatus("reviewLoadError", "error");
  }
}

async function openUniversityReviews(university) {
  state.activeReviewUniversity = university;
  const panel = document.getElementById("review-panel");
  const schoolText = schoolLabels(university, state.language);
  document.getElementById("review-school-name").textContent = schoolText.primary;
  document.getElementById("review-form").reset();
  panel.hidden = false;
  document.body.classList.add("review-open");
  updateReviewAuthState();
  await loadUniversityComments(university.id);
  document.getElementById("review-body").focus();
}

function closeUniversityReviews() {
  document.getElementById("review-panel").hidden = true;
  document.body.classList.remove("review-open");
  state.activeReviewUniversity = null;
  setReviewStatus("");
}

function updateReviewAuthState() {
  const form = document.getElementById("review-form");
  const author = document.getElementById("review-author");
  const submit = document.getElementById("review-submit");
  const anonymous = document.getElementById("review-anonymous");
  if (!form || !submit) return;
  const signedIn = Boolean(state.user);
  if (author) {
    author.disabled = true;
    if (!signedIn) author.value = t("signIn");
    else if (anonymous?.checked) author.value = "good people";
    else author.value = state.user.displayName || t("accountTitle");
  }
  submit.textContent = signedIn ? t("reviewSubmitButton") : t("signIn");
  if (!document.getElementById("review-panel")?.hidden && !signedIn) {
    setReviewStatus("authRequiredForComments", "error");
  }
}

function setupReviewPanel() {
  document.querySelectorAll("[data-review-close]").forEach((button) => {
    button.addEventListener("click", closeUniversityReviews);
  });
  const form = document.getElementById("review-form");
  if (!form || form.dataset.bound === "true") return;
  form.dataset.bound = "true";
  document
    .getElementById("review-anonymous")
    ?.addEventListener("change", updateReviewAuthState);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const university = state.activeReviewUniversity;
    const endpoint = university ? commentsEndpoint(university.id) : "";
    if (!endpoint) {
      setReviewStatus("reviewUnavailable", "error");
      return;
    }
    if (!state.authToken || !state.user) {
      openAuthPanel(t("authRequiredForComments"));
      setReviewStatus("authRequiredForComments", "error");
      return;
    }
    const button = document.getElementById("review-submit");
    button.disabled = true;
    setReviewStatus("reviewSending");
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          body: document.getElementById("review-body").value.trim(),
          anonymous: document.getElementById("review-anonymous").checked,
        }),
      });
      if (!response.ok) throw new Error("comment failed");
      form.reset();
      updateReviewAuthState();
      await loadUniversityComments(university.id);
      setReviewStatus("reviewSubmitSuccess", "success");
    } catch {
      setReviewStatus("reviewSubmitError", "error");
    } finally {
      button.disabled = false;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("review-panel").hidden) {
      closeUniversityReviews();
    }
  });
}

function renderCounts(records, universities) {
  const counts = {
    all: records.length + universities.length,
    open: 0,
    upcoming: 0,
    future: 0,
    closed: 0,
    exception: universities.filter(isExceptionUniversity).length,
    unknown: universities.length,
  };
  records.forEach((record) => {
    counts[getStatus(record)] += 1;
  });
  Object.entries(counts).forEach(([status, count]) => {
    const node = document.getElementById(`count-${status}`);
    if (node) node.textContent = count;
  });
  const mobileOpen = document.getElementById("mobile-open-count");
  const mobileUpcoming = document.getElementById("mobile-upcoming-count");
  if (mobileOpen) mobileOpen.textContent = counts.open;
  if (mobileUpcoming) mobileUpcoming.textContent = counts.upcoming;
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
    container.appendChild(createUniversityGroup([...exceptionUniversities], "exception"));
  }
  if ((state.status === "unknown" || hasActiveSearch()) && baseUniversities.length) {
    container.appendChild(createUniversityGroup([...baseUniversities]));
  }

  emptyState.hidden =
    !activeNonStatusFilter() ||
    records.length > 0 ||
    (state.status === "exception" && exceptionUniversities.length > 0) ||
    ((state.status === "unknown" || hasActiveSearch()) && baseUniversities.length > 0);
  document.getElementById("hero-open-count").textContent = counts.open;
  document.querySelectorAll("[data-mobile-sort]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mobileSort === state.sort);
  });
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
  history.replaceState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}${location.hash}`);
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
  state.rankLimit = ["30", "50", "100", "150", "200"].includes(params.get("rank"))
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
  document.querySelectorAll(".favorite-button[data-favorite-key]").forEach((button) => {
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
    if (translated !== node.dataset.i18nPlaceholder) node.placeholder = translated;
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
  document.getElementById("theme-toggle").setAttribute(
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
  if (!siteKey || document.querySelector('script[data-gradwindow-turnstile]')) {
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

function setupAuthPanel() {
  document.getElementById("auth-toggle")?.addEventListener("click", () => {
    openAuthPanel();
  });
  document.querySelectorAll("[data-auth-close]").forEach((button) => {
    button.addEventListener("click", closeAuthPanel);
  });
  document.getElementById("auth-request-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = document.getElementById("auth-request-button");
    const email = document.getElementById("auth-email").value.trim();
    button.disabled = true;
    try {
      await requestLoginCode(email);
      document.getElementById("auth-code").focus();
    } catch {
      setAuthStatus(t("authError"), "error");
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("auth-verify-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = document.getElementById("auth-verify-button");
    const email = document.getElementById("auth-email").value.trim();
    const code = document.getElementById("auth-code").value.trim();
    button.disabled = true;
    try {
      await verifyLoginCode(email, code);
    } catch {
      setAuthStatus(t("authError"), "error");
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("profile-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = document.getElementById("profile-save-button");
    button.disabled = true;
    try {
      await saveProfile();
    } catch {
      setAuthStatus(t("authError"), "error");
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("auth-logout-button")?.addEventListener("click", signOut);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("auth-panel")?.hidden) {
      closeAuthPanel();
    }
  });
  state.authToken = localStorage.getItem(AUTH_TOKEN_KEY) || "";
  updateAuthUi();
  refreshMe();
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
      state.language === "zh" ? "官方申请目录" : "Official admissions directory";
    const mobileLink = document.getElementById("mobile-deadline-link");
    if (mobileLink) mobileLink.removeAttribute("target");
    const mobileSchool = document.getElementById("mobile-deadline-school");
    const mobileDate = document.getElementById("mobile-deadline-date");
    const mobileNote = document.getElementById("mobile-deadline-note");
    if (mobileSchool) mobileSchool.textContent =
      state.language === "zh" ? "官方申请目录" : "Official admissions directory";
    if (mobileDate) mobileDate.textContent = "TOP 200";
    if (mobileNote) mobileNote.textContent = "";
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
  const mobileLink = document.getElementById("mobile-deadline-link");
  const mobileSchool = document.getElementById("mobile-deadline-school");
  const mobileDate = document.getElementById("mobile-deadline-date");
  const mobileNote = document.getElementById("mobile-deadline-note");
  if (mobileLink) {
    mobileLink.href = safeUrl(futureDeadline.applicationUrl) || "#application-groups";
    mobileLink.target = safeUrl(futureDeadline.applicationUrl) ? "_blank" : "";
    mobileLink.rel = "noreferrer";
  }
  if (mobileSchool) mobileSchool.textContent =
    schoolLabels(futureDeadline, state.language).primary;
  if (mobileDate) mobileDate.textContent = formatDate(futureDeadline.closesAt);
  if (mobileNote) mobileNote.textContent = deadlineNote(
    futureDeadline,
    getStatus(futureDeadline),
  );
}

function setMobileNavActive(name) {
  document.querySelectorAll("[data-mobile-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mobileNav === name);
  });
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
    setMobileNavActive("search");
    resetPages();
    syncUrl();
    render();
  });
  document.getElementById("ranking-filter").addEventListener("change", (event) => {
    state.ranking = event.target.value;
    state.status = state.ranking === "qs" ? "open" : "unknown";
    state.region = "all";
    state.intake = "all";
    if (state.ranking !== "qs") state.sort = "rank";
    resetPages();
    refreshFilterOptions();
    updateRankRangeOptions();
    syncUrl();
    document.querySelectorAll(".status-tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.status === state.status);
    });
    render();
  });
  document.getElementById("region-filter").addEventListener("change", (event) => {
    state.region = event.target.value;
    resetPages();
    syncUrl();
    render();
  });
  document.getElementById("intake-filter").addEventListener("change", (event) => {
    state.intake = event.target.value;
    resetPages();
    syncUrl();
    render();
  });
  document.getElementById("rank-range-filter").addEventListener("change", (event) => {
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
      document
        .querySelectorAll(".status-tab")
        .forEach((tab) => tab.classList.toggle("active", tab === button));
      render();
    });
  });
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
        document.querySelectorAll(".status-tab").forEach((tab) => {
          tab.classList.toggle("active", tab.dataset.status === "open");
        });
        resetPages();
        syncUrl();
        render();
        document.getElementById("application-board").scrollIntoView({ behavior: "smooth" });
      } else if (destination === "search") {
        document.getElementById("application-board").scrollIntoView({ behavior: "smooth" });
        setTimeout(() => document.getElementById("search-input")?.focus(), 250);
      } else if (destination === "favorites") {
        state.favoritesOnly = true;
        resetPages();
        syncUrl();
        render();
        document.getElementById("application-groups").scrollIntoView({ behavior: "smooth" });
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
        schoolAliasesZh: university.schoolAliasesZh || record.schoolAliasesZh || [],
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
    if (selectedRankingDefinition().available === false) state.ranking = "qs";
    if (
      state.ranking !== "qs" &&
      !new URLSearchParams(location.search).has("status")
    ) {
      state.status = "unknown";
    }
    updateRankingAvailability();

    refreshFilterOptions();
    const legacyIntake = state.intake;
    const matchingLegacyRecord = state.data.find(
      (record) => record.intake === legacyIntake,
    );
    if (matchingLegacyRecord) {
      state.intake = canonicalIntake(matchingLegacyRecord).key;
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
    setupSubscription();
    bindEvents();
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
