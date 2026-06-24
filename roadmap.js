import { I18N } from "./i18n.js?v=20260622-i18n";

const VISITOR_KEY = "gradwindow:roadmap-visitor";
const state = {
  language: localStorage.getItem("gradwindow:language") || "zh",
  theme: localStorage.getItem("gradwindow:theme") || "light",
  config: window.GRADWINDOW_CONFIG || {},
  proposals: [],
  serviceAvailable: false,
};

function t(key) {
  return I18N[state.language]?.[key] || I18N.en[key] || key;
}

function visitorId() {
  let value = localStorage.getItem(VISITOR_KEY);
  if (!value) {
    value = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${crypto.getRandomValues(new Uint32Array(1))[0]}`;
    localStorage.setItem(VISITOR_KEY, value);
  }
  return value;
}

function apiUrl(path) {
  const base = String(state.config.roadmapUrl || "").replace(/\/$/, "");
  return base ? `${base}${path}` : "";
}

function applyTranslations() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  });
  document.getElementById("language-toggle").textContent = state.language === "zh" ? "EN" : "中文";
  document.getElementById("theme-toggle").setAttribute("aria-label", t(state.theme === "dark" ? "switchToLight" : "switchToDark"));
  document.title = `GradWindow · ${t("roadmapTitle")}`;
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("gradwindow:theme", theme);
  applyTranslations();
}

function textFor(proposal, field) {
  const value = proposal[field];
  if (value && typeof value === "object") return value[state.language] || value.en || value.zh || "";
  return String(value || "");
}

function makeElement(tag, options = {}) {
  const element = document.createElement(tag);
  if (options.className) element.className = options.className;
  if (options.text !== undefined) element.textContent = String(options.text);
  return element;
}

function proposalCard(proposal) {
  const card = makeElement("article", { className: "roadmap-card" });
  const top = makeElement("div", { className: "roadmap-card-top" });
  const copy = makeElement("div");
  copy.append(
    makeElement("h3", { text: textFor(proposal, "title") }),
    makeElement("p", { className: "roadmap-description", text: textFor(proposal, "description") }),
  );
  const vote = makeElement("button", { className: "vote-button", text: proposal.viewerVoted ? t("roadmapVoted") : t("roadmapVote") });
  vote.type = "button";
  vote.disabled = Boolean(proposal.viewerVoted) || !state.serviceAvailable;
  vote.dataset.proposalId = proposal.id;
  top.append(copy, vote);
  const footer = makeElement("div", { className: "roadmap-card-footer" });
  const count = makeElement("strong", { className: "vote-count", text: `${proposal.votes || 0}` });
  footer.append(count, makeElement("span", { text: t("roadmapVotes") }));
  if (proposal.source === "owner") {
    const progress = Math.max(0, Math.min(100, Number(proposal.progress || 0)));
    const work = makeElement("div", { className: "roadmap-progress" });
    const meta = makeElement("div", { className: "roadmap-progress-meta" });
    meta.append(makeElement("span", { text: t(`roadmapStatus${proposal.status || "planned"}`) }), makeElement("strong", { text: `${progress}%` }));
    const track = makeElement("div", { className: "roadmap-progress-track" });
    const fill = makeElement("div", { className: "roadmap-progress-fill" });
    fill.style.width = `${progress}%`;
    track.appendChild(fill);
    work.append(meta, track);
    card.append(top, work, footer);
  } else {
    card.append(top, footer);
  }
  return card;
}

function render() {
  const owner = state.proposals.filter((item) => item.source === "owner");
  const community = state.proposals.filter((item) => item.source === "community");
  const ownerTarget = document.getElementById("owner-proposals");
  const communityTarget = document.getElementById("community-proposals");
  ownerTarget.replaceChildren(...owner.map(proposalCard));
  communityTarget.replaceChildren(...community.map(proposalCard));
  updateCommunityToggle(community.length);
  document.querySelectorAll(".vote-button").forEach((button) => {
    button.addEventListener("click", () => submitVote(button.dataset.proposalId));
  });
}

function updateCommunityToggle(count) {
  const expanded = !document.getElementById("community-proposals").hidden;
  document.getElementById("community-toggle-label").textContent = count
    ? `${t(expanded ? "roadmapCollapse" : "roadmapExpand")} (${count})`
    : t("roadmapNoCommunity");
}

function setStatus(key, tone = "") {
  const node = document.getElementById("roadmap-status");
  node.className = `roadmap-notice ${tone}`;
  node.textContent = key ? t(key) : "";
}

async function loadProposals() {
  const fallback = await fetch("./data/roadmap-proposals.json").then((response) => response.json());
  state.proposals = fallback.proposals.map((proposal) => ({ ...proposal, source: "owner", votes: 0, viewerVoted: false }));
  const endpoint = apiUrl("/roadmap");
  if (!endpoint) {
    setStatus("roadmapUnavailable");
    render();
    return;
  }
  try {
    const response = await fetch(endpoint, { headers: { "X-GradWindow-Visitor": visitorId() } });
    if (!response.ok) throw new Error("roadmap unavailable");
    const payload = await response.json();
    state.proposals = payload.proposals;
    state.serviceAvailable = true;
    setStatus("");
  } catch {
    setStatus("roadmapUnavailable");
  }
  render();
}

async function submitVote(proposalId) {
  if (!state.serviceAvailable) return;
  try {
    const response = await fetch(apiUrl("/roadmap/votes"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposalId, visitorId: visitorId() }),
    });
    if (response.status === 409) {
      setStatus("roadmapAlreadyVoted", "error");
      await loadProposals();
      return;
    }
    if (!response.ok) throw new Error("vote failed");
    await loadProposals();
  } catch {
    setStatus("roadmapVoteError", "error");
  }
}

function loadTurnstile() {
  const siteKey = state.config.turnstileSiteKey;
  if (!siteKey || document.querySelector("script[data-roadmap-turnstile]")) return;
  window.gradwindowRoadmapTurnstileError = () => {
    setStatus("roadmapTurnstileError", "error");
  };
  const widget = makeElement("div", { className: "cf-turnstile" });
  widget.setAttribute("data-sitekey", siteKey);
  widget.setAttribute("data-action", "turnstile-spin-v1");
  widget.setAttribute("data-theme", state.theme === "dark" ? "dark" : "light");
  widget.setAttribute("data-error-callback", "gradwindowRoadmapTurnstileError");
  widget.setAttribute("data-expired-callback", "gradwindowRoadmapTurnstileError");
  widget.setAttribute("data-timeout-callback", "gradwindowRoadmapTurnstileError");
  document.getElementById("roadmap-turnstile").appendChild(widget);
  const script = document.createElement("script");
  script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js";
  script.async = true;
  script.defer = true;
  script.onerror = () => setStatus("roadmapTurnstileError", "error");
  script.dataset.roadmapTurnstile = "true";
  document.head.appendChild(script);
}

function bindEvents() {
  document.getElementById("language-toggle").addEventListener("click", () => {
    state.language = state.language === "zh" ? "en" : "zh";
    localStorage.setItem("gradwindow:language", state.language);
    applyTranslations();
    render();
  });
  document.getElementById("theme-toggle").addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
  document.getElementById("community-toggle").addEventListener("click", () => {
    const target = document.getElementById("community-proposals");
    target.hidden = !target.hidden;
    document.getElementById("community-toggle").setAttribute("aria-expanded", String(!target.hidden));
    updateCommunityToggle(state.proposals.filter((item) => item.source === "community").length);
  });
  document.getElementById("roadmap-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.serviceAvailable) {
      setStatus("roadmapUnavailable", "error");
      return;
    }
    const button = document.getElementById("roadmap-submit");
    button.disabled = true;
    try {
      const response = await fetch(apiUrl("/roadmap/proposals"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: document.getElementById("roadmap-idea-title").value.trim(),
          description: document.getElementById("roadmap-idea-description").value.trim(),
          visitorId: visitorId(),
          turnstileToken: document.querySelector('[name="cf-turnstile-response"]')?.value || "",
        }),
      });
      if (!response.ok) throw new Error("proposal failed");
      event.target.reset();
      if (window.turnstile) window.turnstile.reset();
      setStatus("roadmapSubmitSuccess", "success");
      await loadProposals();
      document.getElementById("community-proposals").hidden = false;
      document.getElementById("community-toggle").setAttribute("aria-expanded", "true");
      updateCommunityToggle(state.proposals.filter((item) => item.source === "community").length);
    } catch {
      setStatus("roadmapSubmitError", "error");
    } finally {
      button.disabled = false;
    }
  });
}

setTheme(state.theme);
applyTranslations();
bindEvents();
loadTurnstile();
loadProposals();
