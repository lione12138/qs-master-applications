import { t } from "./strings.js";
import { makeElement, makeLink, parseDate } from "./dom.js";

// Build "add to calendar" links and downloads for a single application window.
// Pure with respect to page state: everything derives from the record. The
// URL builders and icsFileBody are exported for the frontend contract tests.

export function googleCalendarUrl(record) {
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
  ]
    .filter(Boolean)
    .join("\n");
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates: `${start}/${end}`,
    details,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

export function outlookCalendarUrl(record) {
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
  ]
    .filter(Boolean)
    .join("\n");
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

export function icsFileBody(record, now = new Date()) {
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
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//GradWindow//Application Deadline//CN",
    "BEGIN:VEVENT",
    `UID:${record.id}@gradwindow`,
    `DTSTAMP:${now.toISOString().replaceAll(/[-:]/g, "").split(".")[0]}Z`,
    `DTSTART;VALUE=DATE:${start}`,
    `DTEND;VALUE=DATE:${end}`,
    `SUMMARY:${escapeIcs(`${record.dataStatus === "predicted" ? "[ESTIMATE] " : ""}${record.school} ${record.program} application deadline`)}`,
    `DESCRIPTION:${escapeIcs(`${record.dataStatus === "predicted" ? "Unofficial calendar-date estimate. Confirm on the official website.\n" : ""}Application: ${record.applicationUrl}\nSource: ${record.sourceUrl}`)}`,
    `URL:${record.applicationUrl}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
}

function downloadIcs(record) {
  const body = icsFileBody(record);
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

export function makeCalendarMenu(record) {
  const menu = makeElement("details", { className: "calendar-menu" });
  const summary = makeElement("summary", {
    className: "calendar-menu-trigger",
    title: t("calendarOptions"),
  });
  summary.append(
    makeElement("span", { className: "calendar-menu-icon" }),
    makeElement("span", {
      className: "calendar-menu-label",
      text: t("addCalendar"),
    }),
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
    makeLink(
      t("googleCalendar"),
      googleCalendarUrl(record),
      "calendar-menu-item",
    ),
    makeLink(
      t("outlookCalendar"),
      outlookCalendarUrl(record),
      "calendar-menu-item",
    ),
    apple,
    android,
    ics,
  );
  menu.append(summary, options);
  return menu;
}
