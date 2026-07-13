import { translate } from "./i18n.js?v=20260622-i18n";

const state = {
  language: "en",
  theme: "light",
};

function t(key) {
  return translate(state.language, key);
}

function applyStaticTranslations() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const translated = t(node.dataset.i18n);
    if (translated !== node.dataset.i18n) node.textContent = translated;
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
  document.title =
    state.language === "zh" ? "GradWindow · 联系" : "GradWindow · Contact";
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  localStorage.setItem("gradwindow:theme", state.theme);
  const button = document.getElementById("theme-toggle");
  if (button) button.textContent = state.theme === "dark" ? "☀" : "☾";
}

function updateMailLink() {
  const button = document.querySelector(".contact-mail-button");
  const subject = document.getElementById("contact-subject")?.value.trim();
  const message = document.getElementById("contact-message")?.value.trim();
  if (!button) return;
  const params = new URLSearchParams();
  params.set("subject", subject || t("contactSubjectPlaceholder"));
  if (message) params.set("body", message);
  button.href = `mailto:lionel8888888@gmail.com?${params.toString()}`;
}

function init() {
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
  updateMailLink();

  document.getElementById("language-toggle").addEventListener("click", () => {
    state.language = state.language === "en" ? "zh" : "en";
    localStorage.setItem("gradwindow:language", state.language);
    applyStaticTranslations();
    updateMailLink();
  });
  document.getElementById("theme-toggle").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme();
  });
  document
    .getElementById("contact-subject")
    ?.addEventListener("input", updateMailLink);
  document
    .getElementById("contact-message")
    ?.addEventListener("input", updateMailLink);
}

init();
