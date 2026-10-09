export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const diffMs = date.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const minutes = Math.round(abs / 60_000);
  if (minutes < 1) return rtf.format(Math.round(diffMs / 1000), "second");
  if (minutes < 60) return rtf.format(Math.sign(diffMs) * minutes, "minute");
  const hours = Math.round(abs / 3_600_000);
  if (hours < 24) return rtf.format(Math.sign(diffMs) * hours, "hour");
  const days = Math.round(abs / 86_400_000);
  if (days < 30) return rtf.format(Math.sign(diffMs) * days, "day");
  return formatDate(value);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatConfidence(value: number): string {
  return value.toFixed(2);
}

/** Duration between two ISO timestamps, or null when either is unusable. */
export function durationBetween(
  start: string | null | undefined,
  end: string | null | undefined,
): number | null {
  if (!start || !end) return null;
  const from = Date.parse(start);
  const to = Date.parse(end);
  if (!Number.isFinite(from) || !Number.isFinite(to)) return null;
  const delta = to - from;
  return delta < 0 ? null : delta;
}

/** Formats a duration as `48s`, `2m 14s` or `1h 03m`. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return "—";
  const total = Math.round(ms / 1000);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes < 60) return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function truncate(value: string, max = 160): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

export function displayCompany(name: string | null, domain: string): string {
  return name && name.trim() ? name : domain;
}

// Mirrors DiscoveryRequest.normalize_domain in backend/app/schemas/prospect.py.
export function normalizeDomain(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .split("/")[0];
}

export function isValidDomain(value: string): boolean {
  const normalized = normalizeDomain(value);
  return normalized.length >= 3 && normalized.includes(".") && !normalized.includes(" ");
}

export function numericEntries(
  breakdown: Record<string, unknown>,
): Array<[string, number]> {
  return Object.entries(breakdown).filter(
    (entry): entry is [string, number] => typeof entry[1] === "number",
  );
}

export function otherEntries(
  breakdown: Record<string, unknown>,
): Array<[string, unknown]> {
  return Object.entries(breakdown).filter(([, value]) => typeof value !== "number");
}

export function stringifyValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Token-level expansions applied when humanizing arbitrary keys. */
const KEY_WORD_EXPANSIONS: Record<string, string> = {
  min: "Minimum",
  max: "Maximum",
  avg: "Average",
  num: "Number",
  emp: "Employees",
  desc: "Description",
  hq: "HQ",
};

/**
 * Turn an arbitrary characteristic key into a readable label
 * ("min_headcount" → "Minimum headcount", "region" → "Region").
 * Expansions are per-word and casing is sentence-style, so any key from
 * the API works — nothing is special-cased by full key name.
 */
export function humanizeKey(key: string): string {
  const words = key
    .trim()
    .split(/[_\s-]+/)
    .filter(Boolean);
  const rendered = words.map((word, index) => {
    const expanded = KEY_WORD_EXPANSIONS[word.toLowerCase()];
    if (expanded) return expanded;
    const lower = word.toLowerCase();
    return index === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
  });
  return rendered.join(" ") || key;
}
