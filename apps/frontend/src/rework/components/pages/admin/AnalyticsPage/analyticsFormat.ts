// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type { TFunction } from "i18next";
import type {
  AnalyticsTeamRow,
  AnalyticsTeamUsageRow,
  BucketPoint,
  PeriodValue,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

/** Written in a cell or tile that has no value. */
export const NO_VALUE = "—";

export type ValueFormat = "count" | "decimal" | "percent" | "eur" | "compact" | "days";
/** relative: % change; points: difference of two rates; absolute: difference of two counts. */
export type DeltaKind = "relative" | "points" | "absolute";

export function formatValue(value: number, format: ValueFormat, lng: string): string {
  switch (format) {
    case "percent":
      return new Intl.NumberFormat(lng, { style: "percent", maximumFractionDigits: 1 }).format(value);
    case "eur":
      return new Intl.NumberFormat(lng, {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: value >= 100 ? 0 : 2,
      }).format(value);
    case "decimal":
      return new Intl.NumberFormat(lng, { maximumFractionDigits: 1 }).format(value);
    case "days":
      return new Intl.NumberFormat(lng, {
        style: "unit",
        unit: "day",
        unitDisplay: "long",
        maximumFractionDigits: 1,
      }).format(value);
    case "compact":
      return new Intl.NumberFormat(lng, { notation: "compact", maximumFractionDigits: 1 }).format(value);
    default:
      return new Intl.NumberFormat(lng, { maximumFractionDigits: 0 }).format(value);
  }
}

export interface PeriodDelta {
  label: string;
  tone: "positive" | "negative" | "neutral";
  /** Undefined for a change that rounds to zero. */
  direction?: "up" | "down";
}

/** The change against the previous period, or undefined when either side has no data. */
export function periodDelta(
  period: PeriodValue | null | undefined,
  kind: DeltaKind,
  t: TFunction,
  lng: string,
  { lowerIsBetter = false, neutral = false }: { lowerIsBetter?: boolean; neutral?: boolean } = {},
): PeriodDelta | undefined {
  const current = period?.current;
  const previous = period?.previous;
  if (current == null || previous == null) return undefined;
  if (kind === "relative" && previous === 0) return undefined;
  const raw = kind === "relative" ? (current - previous) / previous : current - previous;
  // Round as displayed, so a "+0 %" is neither colored nor signed.
  const step = kind === "absolute" ? 10 : kind === "points" ? 1000 : 100;
  const change = Math.round(raw * step) / step || 0;
  const sign = change > 0 ? "+" : "";
  const label =
    kind === "relative"
      ? t("rework.analytics.delta.relative", {
          value: sign + new Intl.NumberFormat(lng, { style: "percent", maximumFractionDigits: 0 }).format(change),
        })
      : kind === "points"
        ? t("rework.analytics.delta.points", {
            value: sign + new Intl.NumberFormat(lng, { maximumFractionDigits: 1 }).format(change * 100),
          })
        : t("rework.analytics.delta.absolute", {
            value: sign + new Intl.NumberFormat(lng, { maximumFractionDigits: 1 }).format(change),
          });
  const better = lowerIsBetter ? change < 0 : change > 0;
  const tone = neutral || change === 0 ? "neutral" : better ? "positive" : "negative";
  return { label, tone, direction: change > 0 ? "up" : change < 0 ? "down" : undefined };
}

/** Whether a series crosses days (hour buckets) or years (month buckets), so labels stay distinct. */
export interface BucketSpan {
  days: boolean;
  years: boolean;
}

export function bucketSpan(points: { start: string }[] | undefined): BucketSpan {
  const first = points?.[0]?.start ?? "";
  const last = points?.[points.length - 1]?.start ?? "";
  return { days: first.slice(0, 10) !== last.slice(0, 10), years: first.slice(0, 4) !== last.slice(0, 4) };
}

/** The x-axis label of a calendar bucket; `start` is already in the requested time zone. */
export function formatBucketLabel(
  start: string,
  bucket: string,
  lng: string,
  t: TFunction,
  span: BucketSpan = { days: false, years: false },
): string {
  const [datePart, timePart] = start.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const hour = timePart ? Number(timePart.split(":")[0]) : 0;
  const date = new Date(Date.UTC(y, m - 1, d, hour));
  const fmt = (options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(lng, { ...options, timeZone: "UTC" }).format(date);
  switch (bucket) {
    case "hour":
      return fmt(span.days ? { day: "2-digit", month: "2-digit", hour: "numeric" } : { hour: "numeric" });
    case "week":
      return t("rework.analytics.buckets.week", { week: isoWeek(date) });
    case "month":
      return fmt(span.years ? { month: "short", year: "2-digit" } : { month: "short" });
    default:
      return fmt({ day: "2-digit", month: "2-digit" });
  }
}

export function isoWeek(date: Date): number {
  const thursday = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  thursday.setUTCDate(thursday.getUTCDate() + 4 - (thursday.getUTCDay() || 7));
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1);
  return Math.ceil(((thursday.getTime() - yearStart) / 86400000 + 1) / 7);
}

/** The browser's IANA zone, so buckets and days follow the viewer's calendar. */
export function viewerTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Paris";
}

/** Calendar points as chart rows: one labelled value per series key. */
export function bucketSeries(
  points: BucketPoint[] | undefined,
  bucket: string | undefined,
  series: Record<string, string>,
  lng: string,
  t: TFunction,
): { date: string; values: Record<string, number> }[] {
  const span = bucketSpan(points);
  return (points ?? []).map((p) => ({
    date: formatBucketLabel(p.start, bucket ?? "day", lng, t, span),
    values: Object.fromEntries(Object.entries(series).map(([key, label]) => [label, p.values[key] ?? 0])),
  }));
}

export interface TeamRow {
  teamId: string;
  name: string;
  members: number | null;
  active: number;
  share: number | null;
  messages: number;
  change: number | null;
}

/** Activity per team space, joined with the catalog so teams without activity are listed too. */
export function teamRows(rows: AnalyticsTeamUsageRow[], catalog: AnalyticsTeamRow[], teamIds: string[]): TeamRow[] {
  const byId = new Map(rows.map((r) => [r.team_id, r]));
  const known = new Map(catalog.map((c) => [c.team_id, c]));
  const listed = catalog.filter((c) => teamIds.length === 0 || teamIds.includes(c.team_id));
  const ids = new Set([...listed.map((c) => c.team_id), ...rows.map((r) => r.team_id)]);
  return [...ids]
    .map((id) => {
      const usage = byId.get(id);
      const count = known.get(id)?.member_count ?? null;
      const active = usage?.active_members ?? 0;
      const previous = usage?.messages_previous ?? 0;
      const messages = usage?.messages ?? 0;
      return {
        teamId: id,
        name: usage?.name ?? known.get(id)?.name ?? id,
        members: count,
        active,
        share: count ? Math.min(1, active / count) : null,
        messages,
        change: previous > 0 ? (messages - previous) / previous : null,
      };
    })
    .sort((a, b) => b.messages - a.messages || a.name.localeCompare(b.name));
}
