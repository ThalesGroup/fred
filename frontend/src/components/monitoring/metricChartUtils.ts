// Copyright Thales 2025
// Apache-2.0

import dayjs from "dayjs";
import { Theme, alpha } from "@mui/material/styles";

/** Keep it string to match OpenAPI client. */
export type PrecisionStr = string;

export function getPrecisionForRange(start: Date | number, end: Date | number): PrecisionStr {
  const s = typeof start === "number" ? start : (start as Date).getTime();
  const e = typeof end === "number" ? end : (end as Date).getTime();
  const diffMs = e - s;
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  const diffHours = diffMs / (1000 * 60 * 60);

  if (diffMs <= 10_000) return "sec";
  if (diffHours < 10) return "min";
  if (diffDays <= 3) return "hour";
  return "day";
}

export function formatBytes(n: number) {
  if (!Number.isFinite(n)) return "-";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let v = n, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(2)} ${units[i]}`;
}

export function buildStackedByCategory(
  metrics: { precision?: string; buckets?: any[] } | undefined,
  valueKey: "store_size_bytes_sum" | "docs_count_sum"
) {
  const byTs = new Map<number, Record<string, number>>();
  const keys = new Set<string>();
  for (const b of metrics?.buckets ?? []) {
    const ts = new Date(b.timestamp).getTime();
    const cat = (b.group?.category ?? "other") as string;
    const val = Number(b.aggregations?.[valueKey] ?? 0);
    keys.add(cat);
    const row = byTs.get(ts) ?? { ts };
    row[cat] = (row[cat] ?? 0) + val;
    byTs.set(ts, row);
  }
  const data = Array.from(byTs.entries()).sort((a, b) => a[0] - b[0]).map(([ts, row]) => ({ ts, ...row }));
  return { data, keys: Array.from(keys).sort() };
}

export function tsTickFormatter(precision: string) {
  return (ts: number) => {
    const d = dayjs(ts);
    if (precision === "sec") return d.format("HH:mm:ss");
    if (precision === "min") return d.format("HH:mm");
    if (precision === "hour") return d.format("MMM D HH:mm");
    return d.format("YYYY-MM-DD");
  };
}

/* -------------------------------------------------------------------------- */
/* THEME-DRIVEN CHART STYLES                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Returns a soft, theme-aware list of series colors (RGBA) derived from theme.palette.chart.
 * Pass a `count` to ensure you get at least that many colors (it cycles if needed).
 */
export function chartSeriesPalette(theme: Theme, count?: number): string[] {
  // use your extended theme.palette.chart (from your theme file)
  const c = (theme.palette as any).chart || {};
  const bases: string[] = [
    c.primary, c.secondary,
    c.blue, c.green, c.orange, c.purple, c.red, c.yellow,
    c.highBlue, c.mediumBlue, c.highGreen, c.mediumGreen,
  ].filter(Boolean);

  if (bases.length === 0) {
    // fallback to MUI main colors if chart palette is missing
    bases.push(
      theme.palette.primary.main,
      theme.palette.secondary.main,
      theme.palette.success.main,
      theme.palette.info.main,
      theme.palette.warning.main,
      theme.palette.error.main
    );
  }

  const baseA = theme.palette.mode === "dark" ? 0.28 : 0.22; // soft fills
  const soft = bases.map((hex) => alpha(hex, baseA));

  if (!count) return soft;
  const out: string[] = [];
  for (let i = 0; i < count; i++) out.push(soft[i % soft.length]);
  return out;
}

/** Theme-consistent axis tick styling */
export function axisTickProps(theme: Theme) {
  return { fontSize: 11, fill: theme.palette.text.secondary };
}

/** Theme-consistent grid stroke */
export function gridStroke(theme: Theme) {
  return theme.palette.divider;
}

/** Legend wrapper style that follows theme text colors */
export function legendStyle(theme: Theme) {
  return { fontSize: 11, color: theme.palette.text.secondary as any };
}

/** Tooltip panel style following theme surfaces */
export function tooltipStyle(theme: Theme) {
  return {
    fontSize: 12,
    backgroundColor: theme.palette.background.paper,
    border: `1px solid ${theme.palette.divider}`,
    borderRadius: 8,
    color: theme.palette.text.primary,
    boxShadow: theme.shadows[2] as any,
    padding: 8,
  };
}

/**
 * Single bar/line color (e.g. token chart) from theme.palette.chart.
 * Change the key here if you prefer "primary" or another chart color.
 */
export function primarySeriesColor(theme: Theme) {
  const c = (theme.palette as any).chart || {};
  const base = c.blue || c.primary || theme.palette.primary.main;
  return alpha(base, theme.palette.mode === "dark" ? 0.7 : 0.55);
}
