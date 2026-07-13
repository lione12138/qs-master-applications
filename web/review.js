import { state } from "./state.js";
import { t } from "./strings.js";
import { acronym, makeElement, visitorId } from "./dom.js";
import { schoolLabels } from "./localization.js";
import { authHeaders, feedbackApiBase, openAuthPanel } from "./auth.js";

// University review panel: per-university comment list plus a signed-in
// comment form. Depends on auth.js for API access and the sign-in prompt;
// auth.js reaches back only through the updateReviewAuthState callback that
// app.js passes to initAuth, so the dependency stays one-way.

const VISITOR_KEY = "gradwindow:visitor";

export function makeReviewButton(university) {
  const button = makeElement("button", {
    className: "icon-button review-button",
    text: t("schoolReviews"),
    title: t("openSchoolReviews"),
  });
  button.type = "button";
  button.addEventListener("click", () => openUniversityReviews(university));
  return button;
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
      makeElement("p", {
        className: "review-empty",
        text: t("reviewNoComments"),
      }),
    );
    return;
  }
  comments.forEach((comment) => {
    const item = makeElement("article", { className: "review-item" });
    const avatar = makeElement("span", {
      className: `review-avatar ${comment.anonymous ? "cat-avatar" : "user-avatar"}`,
      text: comment.anonymous
        ? ""
        : acronym(comment.author || "G").slice(0, 2) || "G",
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
      makeElement("p", {
        className: "review-item-body",
        text: comment.body || "",
      }),
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
      headers: { "X-GradWindow-Visitor": visitorId(VISITOR_KEY) },
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
  document.getElementById("review-school-name").textContent =
    schoolText.primary;
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

export function updateReviewAuthState() {
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

export function setupReviewPanel() {
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
    if (
      event.key === "Escape" &&
      !document.getElementById("review-panel").hidden
    ) {
      closeUniversityReviews();
    }
  });
}
