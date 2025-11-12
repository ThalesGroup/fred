// components/monitoring/dateRangePresets.ts
// Purpose (Fred): Declarative quick ranges to plug into DateRangeControl.

import dayjs, { Dayjs } from "dayjs";
import type { QuickRangeItem } from "./DateRangeControl";

const last =
  (n: number, unit: dayjs.ManipulateType, round?: "hour" | "day" | "none") =>
  (now: Dayjs): [Dayjs, Dayjs] => {
    const end = round === "hour" ? now.endOf("hour") : round === "day" ? now.endOf("day") : now;
    const start =
      round === "hour"
        ? end.subtract(n, unit).startOf("hour")
        : round === "day"
          ? end.subtract(n, unit).startOf("day")
          : end.subtract(n, unit);
    return [start, end];
  };

export const SHORT_QUICK_RANGES: QuickRangeItem[] = [
  { id: "last10m", labelKey: "metrics.range.last10m", labelFallback: "Last 10m", compute: last(10, "minute", "none") },
  { id: "last30m", labelKey: "metrics.range.last30m", labelFallback: "Last 30m", compute: last(30, "minute", "none") },
  { id: "last1h", labelKey: "metrics.range.last1h", labelFallback: "Last 1h", compute: last(1, "hour", "none") },
  { id: "last12h", labelKey: "metrics.range.last12h", labelFallback: "Last 12h", compute: last(12, "hour", "hour") },
  { id: "last24h", labelKey: "metrics.range.last24h", labelFallback: "Last 24h", compute: last(24, "hour", "hour") },
];

export const FULL_QUICK_RANGES: QuickRangeItem[] = [
  ...SHORT_QUICK_RANGES,
  {
    id: "today",
    labelKey: "metrics.range.today",
    labelFallback: "Today",
    compute: (n) => [n.startOf("day"), n.endOf("day")],
  },
  {
    id: "yesterday",
    labelKey: "metrics.range.yesterday",
    labelFallback: "Yesterday",
    compute: (n) => [n.subtract(1, "day").startOf("day"), n.subtract(1, "day").endOf("day")],
  },
  {
    id: "thisWeek",
    labelKey: "metrics.range.thisWeek",
    labelFallback: "This week",
    compute: (n) => [n.startOf("week"), n.endOf("week")],
  },
  {
    id: "thisMonth",
    labelKey: "metrics.range.thisMonth",
    labelFallback: "This month",
    compute: (n) => [n.startOf("month"), n.endOf("month")],
  },
  {
    id: "thisYear",
    labelKey: "metrics.range.thisYear",
    labelFallback: "This year",
    compute: (n) => [n.startOf("year"), n.endOf("year")],
  },
];
