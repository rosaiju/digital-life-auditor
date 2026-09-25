/** Parse "YYYY-MM-DD" as a local calendar date. `new Date("2026-09-25")` is UTC midnight,
 *  which renders as the previous day in the Americas. */
export function parseDateOnly(value: string): Date {
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** Parse a timestamp from the API. The backend stores naive UTC (no "Z"), which JS would
 *  otherwise read as local time. */
export function parseTimestamp(value: string): Date {
  return new Date(/(Z|[+-]\d\d:?\d\d)$/i.test(value) ? value : `${value}Z`);
}

export function formatShortDate(value: string): string {
  return parseDateOnly(value).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** "just now", "5 min ago", "3 h ago", "2 days ago". */
export function timeAgo(value: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - parseTimestamp(value).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
