import { makeElement } from "./dom.js";

const config = window.GRADWINDOW_CONFIG || {};
const apiBase = String(config.roadmapUrl || config.subscribeUrl || "").replace(
  /\/$/,
  "",
);
const keyInput = document.getElementById("admin-api-key");
const statusNode = document.getElementById("admin-status");
const dashboard = document.getElementById("admin-dashboard");
let activeKey = "";

function setStatus(message, tone = "") {
  statusNode.textContent = message;
  statusNode.className = `admin-status${tone ? ` ${tone}` : ""}`;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
  }).format(date);
}

function render(payload) {
  document.getElementById("admin-total-votes").textContent = String(
    payload.summary?.totalVotes || 0,
  );
  document.getElementById("admin-unique-voters").textContent = String(
    payload.summary?.uniqueVoters || 0,
  );
  document.getElementById("admin-last-vote").textContent = formatDate(
    payload.summary?.lastVoteAt,
  );
  const rows = (payload.proposals || []).map((proposal) => {
    const row = document.createElement("tr");
    row.append(
      makeElement("td", {
        text: proposal.title?.zh || proposal.title?.en || proposal.id,
      }),
      makeElement("td", {
        text: proposal.source === "owner" ? "官方规划" : "社区建议",
      }),
      makeElement("td", { text: String(proposal.votes || 0) }),
      makeElement("td", { text: formatDate(proposal.firstVoteAt) }),
      makeElement("td", { text: formatDate(proposal.lastVoteAt) }),
    );
    return row;
  });
  document.getElementById("admin-proposals").replaceChildren(...rows);
  dashboard.hidden = false;
}

async function loadStats(key) {
  if (!apiBase) {
    setStatus("统计服务尚未配置。", "error");
    return;
  }
  setStatus("正在加载…");
  try {
    const response = await fetch(`${apiBase}/admin/roadmap/stats`, {
      headers: { Authorization: `Bearer ${key}` },
      cache: "no-store",
    });
    if (response.status === 401) throw new Error("unauthorized");
    if (!response.ok) throw new Error("unavailable");
    render(await response.json());
    setStatus("统计已更新。", "success");
  } catch (error) {
    dashboard.hidden = true;
    setStatus(
      error.message === "unauthorized"
        ? "访问密钥不正确。"
        : "暂时无法读取统计，请稍后重试。",
      "error",
    );
  }
}

document
  .getElementById("admin-auth-form")
  .addEventListener("submit", (event) => {
    event.preventDefault();
    activeKey = keyInput.value.trim();
    keyInput.value = "";
    loadStats(activeKey);
  });

document.getElementById("admin-refresh").addEventListener("click", () => {
  if (activeKey) loadStats(activeKey);
});
