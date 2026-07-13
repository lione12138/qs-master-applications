// Shared DOM, URL, and identity helpers used by the page entry scripts
// (app.js, calendar.js, roadmap.js). These are intentionally free of any
// per-page state so they can be reused without coupling.

export function makeElement(tag, options = {}) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.title) node.title = options.title;
  return node;
}

export function safeUrl(value) {
  try {
    const url = new URL(value, window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

export function makeLink(text, url, className = "") {
  const validUrl = safeUrl(url);
  if (!validUrl) return makeElement("span", { className, text });
  const link = makeElement("a", { className, text });
  link.href = validUrl;
  link.target = "_blank";
  link.rel = "noreferrer";
  return link;
}

export function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

export function acronym(value = "") {
  return String(value)
    .split(/[^A-Za-z0-9]+/)
    .filter(
      (word) => word && !["of", "the", "and"].includes(word.toLowerCase()),
    )
    .map((word) => word[0])
    .join("")
    .toLocaleLowerCase("zh-CN");
}

export function visitorId(storageKey) {
  let value = localStorage.getItem(storageKey);
  if (!value) {
    value = crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${crypto.getRandomValues(new Uint32Array(1))[0]}`;
    localStorage.setItem(storageKey, value);
  }
  return value;
}
