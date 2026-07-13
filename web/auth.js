import { state } from "./state.js";
import { t } from "./strings.js";

// Email-code sign-in, profile, and favourites sync for the tracker page.
// Auth updates page UI it does not own (board, favourite controls, review
// panel), so app.js injects those refreshers via initAuth() instead of this
// module importing app.js back (which would create a cycle).

const AUTH_TOKEN_KEY = "gradwindow:authToken";

let deps = {
  render: () => {},
  updateFavoriteControls: () => {},
  updateReviewAuthState: () => {},
};

export function initAuth(callbacks = {}) {
  deps = { ...deps, ...callbacks };
}

export function feedbackApiBase() {
  const config = window.GRADWINDOW_CONFIG || {};
  return String(config.roadmapUrl || config.subscribeUrl || "").replace(
    /\/$/,
    "",
  );
}

function authApiBase() {
  return feedbackApiBase();
}

export function authHeaders(includeJson = true) {
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

export function updateAuthUi() {
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
    document.getElementById("profile-name").value =
      state.user.displayName || "";
    document.getElementById("profile-country").value = state.user.country || "";
    document.getElementById("profile-intake").value =
      state.user.targetIntake || "";
  }
  deps.updateReviewAuthState();
}

export function openAuthPanel(message = "") {
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
      ...(payload.favorites || []).filter(Boolean),
    ]);
    state.favorites = merged;
    localStorage.setItem("gradwindow:favorites", JSON.stringify([...merged]));
    scheduleFavoriteSync();
  } catch {
    state.user = null;
    saveAuthToken("");
  }
  updateAuthUi();
  deps.updateFavoriteControls();
  deps.render();
}

export function scheduleFavoriteSync() {
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
    ...(payload.favorites || []).filter(Boolean),
  ]);
  localStorage.setItem(
    "gradwindow:favorites",
    JSON.stringify([...state.favorites]),
  );
  setAuthStatus(t("authSignedIn"), "success");
  updateAuthUi();
  deps.updateFavoriteControls();
  deps.render();
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

export function setupAuthPanel() {
  document.getElementById("auth-toggle")?.addEventListener("click", () => {
    openAuthPanel();
  });
  document.querySelectorAll("[data-auth-close]").forEach((button) => {
    button.addEventListener("click", closeAuthPanel);
  });
  document
    .getElementById("auth-request-form")
    ?.addEventListener("submit", async (event) => {
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
  document
    .getElementById("auth-verify-form")
    ?.addEventListener("submit", async (event) => {
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
  document
    .getElementById("profile-form")
    ?.addEventListener("submit", async (event) => {
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
  document
    .getElementById("auth-logout-button")
    ?.addEventListener("click", signOut);
  document.addEventListener("keydown", (event) => {
    if (
      event.key === "Escape" &&
      !document.getElementById("auth-panel")?.hidden
    ) {
      closeAuthPanel();
    }
  });
  state.authToken = localStorage.getItem(AUTH_TOKEN_KEY) || "";
  updateAuthUi();
  refreshMe();
}
