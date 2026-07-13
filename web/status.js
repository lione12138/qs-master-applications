export const UPCOMING_WINDOW_DAYS = 30;

const DAY_MS = 86_400_000;

function parseUtcDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

function localCalendarDate() {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}

export function getApplicationStatus(
  record,
  today = localCalendarDate(),
  upcomingWindowDays = UPCOMING_WINDOW_DAYS,
) {
  if (!record.opensAt || !record.closesAt) return "unknown";

  const opens = parseUtcDate(record.opensAt);
  const closes = parseUtcDate(record.closesAt);
  if (today > closes) return "closed";
  if (today >= opens) return "open";

  const daysToOpen = Math.ceil((opens - today) / DAY_MS);
  return daysToOpen <= upcomingWindowDays ? "upcoming" : "future";
}

export function countUniversitiesByStatus(
  records,
  statusForRecord = getApplicationStatus,
) {
  const universityIds = {
    open: new Set(),
    upcoming: new Set(),
    future: new Set(),
    closed: new Set(),
  };
  records.forEach((record) => {
    const status = statusForRecord(record);
    if (record.universityId && universityIds[status]) {
      universityIds[status].add(record.universityId);
    }
  });
  return Object.fromEntries(
    Object.entries(universityIds).map(([status, ids]) => [status, ids.size]),
  );
}
