/** Presentation helpers. Nothing here calls the API or holds state. */

import type { SearchResult, StandardSummary } from "./api";

/**
 * Relative match strength for a search hit, in 0..1.
 *
 * This exists because the API does **not** return a calibrated confidence, and
 * inventing one would be the single most misleading thing this UI could do.
 * `score` is a reciprocal-rank-fusion value: it depends on how many retrievers
 * fired, on the result-set size, and on the query, so `0.041` is not "4%
 * confident" and rendering it as a percentage would be a fabrication.
 *
 * What can be said honestly is *relative* strength: how this hit compares with
 * the best hit for the same query. The UI labels it as exactly that.
 */
export function matchStrength(result: SearchResult, results: SearchResult[]): number {
  const best = Math.max(...results.map((r) => r.score), 0);
  if (best <= 0) return 0;
  return Math.min(1, Math.max(0, result.score / best));
}

/** Which retrievers found a hit, as a human-readable phrase. */
export function foundByLabel(foundBy: Record<string, number>): string {
  const sources: string[] = [];
  if (foundBy["bm25:chunks"] || foundBy["bm25:standards"]) sources.push("keyword");
  if (foundBy["dense:chunks"]) sources.push("semantic");
  if (foundBy["tfidf:chunks"] || foundBy["tfidf:standards"]) sources.push("tf-idf");
  if (foundBy["exact:standards"]) sources.push("exact code");
  return sources.length ? sources.join(" + ") : "retrieved";
}

export const GRADE_STYLES: Record<string, { badge: string; ring: string; text: string }> = {
  "FULLY COMPLIANT": {
    badge: "bg-emerald-600 text-white",
    ring: "#138808",
    text: "text-emerald-700",
  },
  "MOSTLY COMPLIANT": {
    badge: "bg-lime-600 text-white",
    ring: "#65a30d",
    text: "text-lime-700",
  },
  "PARTIALLY COMPLIANT": {
    badge: "bg-amber-500 text-white",
    ring: "#f59e0b",
    text: "text-amber-700",
  },
  "NON-COMPLIANT": {
    badge: "bg-red-600 text-white",
    ring: "#dc2626",
    text: "text-red-700",
  },
};

export function gradeStyle(grade: string) {
  return (
    GRADE_STYLES[grade] ?? { badge: "bg-muted text-foreground", ring: "#94a3b8", text: "" }
  );
}

export function scorePercent(score: number): number {
  return Math.round(Math.min(1, Math.max(0, score)) * 100);
}

export function formatMs(ms: number): string {
  if (ms < 1) return "<1 ms";
  // One decimal only below 10 ms, where the decimal carries information: the
  // difference between 12 ms and 12.2 ms changes nothing for a reader, and
  // "12.24 ms" in a list of timings reads as noise.
  if (ms < 10) return `${ms.toFixed(1)} ms`;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-IN").format(value);
}

/** Group standards by a key, sorted by count descending. For the dashboard. */
export function countBy<T>(rows: T[], key: (row: T) => string | number | undefined) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = key(row);
    if (value === undefined || value === null || value === "") continue;
    const label = String(value);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

/**
 * Bucket publication years into decades.
 *
 * Decades rather than years on purpose: BIS editions cluster heavily on a few
 * years (revisions land in bursts), so a per-year bar chart is mostly empty
 * space, and the shape of the distribution is what the page is for.
 */
export function byDecade(rows: StandardSummary[]) {
  const buckets = new Map<string, number>();
  for (const row of rows) {
    const year = row.year;
    if (!year || year < 1900) continue;
    const decade = Math.floor(year / 10) * 10;
    const label = `${decade}s`;
    buckets.set(label, (buckets.get(label) ?? 0) + 1);
  }
  return [...buckets.entries()]
    .map(([label, count]) => ({ label, count, decade: parseInt(label, 10) }))
    .sort((a, b) => a.decade - b.decade);
}

export function truncate(text: string, max = 160): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max).trimEnd()}…`;
}

export function statusLabel(row: { is_current: boolean; superseded_by: string }): string {
  if (row.is_current) return "Current";
  return row.superseded_by ? `Superseded by ${row.superseded_by}` : "Superseded";
}
