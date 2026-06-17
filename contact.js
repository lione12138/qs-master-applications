import { I18N } from "./i18n.js";

const state = {
  language: "en",
  theme: "light",
};

function t(key) {
  return I18N[state.language][key] || I18N.en[key] || key;
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
    state.language === "zh" ? "GradWindow · 联系" : "GradWindow · Contact";
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  localStorage.setItem("gradwindow:theme", state.theme);
  const button = document.getElementById("theme-toggle");
  if (button) button.textContent = state.theme === "dark" ? "☀" : "☾";
}

function init() {
  state.language = localStorage.getItem("gradwindow:language") === "zh" ? "zh" : "en";
  const savedTheme = localStorage.getItem("gradwindow:theme");
  state.theme = ["light", "dark"].includes(savedTheme)
    ? savedTheme
    : window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  applyTheme();
  applyStaticTranslations();

  document.getElementById("language-toggle").addEventListener("click", () => {
    state.language = state.language === "en" ? "zh" : "en";
    localStorage.setItem("gradwindow:language", state.language);
    applyStaticTranslations();
  });
  document.getElementById("theme-toggle").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme();
  });
}

init();
