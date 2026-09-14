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

export type TimePresetKey = "last24h" | "last7d" | "last30d" | "today" | "thisWeek" | "thisMonth";

export type CalendarUnit = "day" | "week" | "month";

export interface TimeRange {
  since: string;
  until: string;
  presetKey?: TimePresetKey;
  /** Whole periods away from the preset's current one: 0 is now, -1 the period before. */
  offset?: number;
}

/** A rolling window ending now steps by its own length; a calendar period steps a whole unit, so
 *  "this month" goes back to the previous month, not to the previous 30 days. */
export type PresetPeriod = { kind: "rolling"; durationMs: number } | { kind: "calendar"; unit: CalendarUnit };

export interface TimePreset {
  key: TimePresetKey;
  labelKey: string;
  period: PresetPeriod;
}

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

export const TIME_PRESETS: TimePreset[] = [
  { key: "last24h", labelKey: "rework.analytics.presets.last24h", period: { kind: "rolling", durationMs: DAY } },
  { key: "last7d", labelKey: "rework.analytics.presets.last7d", period: { kind: "rolling", durationMs: 7 * DAY } },
  { key: "last30d", labelKey: "rework.analytics.presets.last30d", period: { kind: "rolling", durationMs: 30 * DAY } },
  { key: "today", labelKey: "rework.analytics.presets.today", period: { kind: "calendar", unit: "day" } },
  { key: "thisWeek", labelKey: "rework.analytics.presets.thisWeek", period: { kind: "calendar", unit: "week" } },
  { key: "thisMonth", labelKey: "rework.analytics.presets.thisMonth", period: { kind: "calendar", unit: "month" } },
];

export function getPreset(key: TimePresetKey): TimePreset {
  return TIME_PRESETS.find((p) => p.key === key)!;
}

/** Local midnight starting the `unit` that contains `date`, moved `offset` whole units. Weeks start on Monday. */
export function startOfUnit(unit: CalendarUnit, date: Date, offset = 0): Date {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  if (unit === "day") {
    d.setDate(d.getDate() + offset);
  } else if (unit === "week") {
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + 7 * offset);
  } else {
    d.setFullYear(d.getFullYear(), d.getMonth() + offset, 1);
  }
  return d;
}

/** The range a preset covers `offset` periods away from now. `until` never goes past now. */
export function resolvePreset(key: TimePresetKey, offset = 0, now = new Date()): TimeRange {
  const { period } = getPreset(key);
  let since: Date;
  let until: Date;
  if (period.kind === "rolling") {
    until = new Date(now.getTime() + offset * period.durationMs);
    since = new Date(until.getTime() - period.durationMs);
  } else {
    since = startOfUnit(period.unit, now, offset);
    const end = startOfUnit(period.unit, now, offset + 1);
    until = end < now ? end : now;
  }
  return { since: since.toISOString(), until: until.toISOString(), presetKey: key, offset };
}

/** Moves a range one period back (-1) or forward (1). A custom range moves by its own length,
 *  and stops at now rather than reaching into the future. */
export function shiftTimeRange(range: TimeRange, direction: -1 | 1, now = new Date()): TimeRange {
  if (range.presetKey) {
    return resolvePreset(range.presetKey, Math.min(0, (range.offset ?? 0) + direction), now);
  }
  const since = Date.parse(range.since);
  const length = Date.parse(range.until) - since;
  const until = Math.min(since + length + direction * length, now.getTime());
  return { since: new Date(until - length).toISOString(), until: new Date(until).toISOString() };
}

/** A custom range ending within the last minute counts as already current — its inputs only
 *  have minute precision. */
export function canShiftForward(range: TimeRange, now = new Date()): boolean {
  if (range.presetKey) return (range.offset ?? 0) < 0;
  return Date.parse(range.until) < now.getTime() - MIN;
}

/** Brings a current preset up to now. A past period or a custom range is fixed and comes back as is,
 *  so a refresh after midnight or a month end never jumps to a different period. */
export function refreshTimeRange(range: TimeRange): TimeRange {
  return range.presetKey && !range.offset ? resolvePreset(range.presetKey) : range;
}
