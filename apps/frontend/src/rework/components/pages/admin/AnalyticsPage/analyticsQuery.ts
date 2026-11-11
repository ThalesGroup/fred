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

import type { TimePresetKey, TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import type { PlatformAccessCondition } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { viewerTimeZone } from "./analyticsFormat";

/** The periods offered wherever analytics or personal usage are shown. */
export const ANALYTICS_PRESETS: TimePresetKey[] = [
  "last7d",
  "last30d",
  "last3Months",
  "last12Months",
  "today",
  "thisWeek",
  "thisMonth",
];

/** Every analytics read caches for five minutes instead of refetching on each tab switch. */
export const KPI_CACHE = { refetchOnMountOrArgChange: 300 } as const;

/** platform: the admin page, any scope. team: a team admin's page, fixed to their team. */
export type AnalyticsMode = "platform" | "team";

/** What every tab reads: the period and the team scope (empty = whole platform). */
export interface AnalyticsTabProps {
  timeRange: TimeRange;
  teamIds: string[];
  /** Team mode hides what only makes sense across teams. Defaults to platform. */
  mode?: AnalyticsMode;
  /** Serialized user filter (platform page only): passed to the reads that can be narrowed to users. */
  userFilter?: string;
  /** Which days the indicators count; every activity read leaves the others out. */
  days: AnalyticsDays;
}

/** The viewer's choice of counted days. Weekends and French public holidays are left out by default. */
export interface AnalyticsDays {
  excludeWeekends: boolean;
  excludeHolidays: boolean;
}

export const DEFAULT_ANALYTICS_DAYS: AnalyticsDays = { excludeWeekends: true, excludeHolidays: true };
const DAYS_STORAGE_KEY = "analytics.days";

/** The stored choice, or the defaults when storage is empty, blocked or holds something else. */
export function loadAnalyticsDays(): AnalyticsDays {
  try {
    const stored = JSON.parse(localStorage.getItem(DAYS_STORAGE_KEY) ?? "null") as Partial<AnalyticsDays> | null;
    return {
      excludeWeekends:
        typeof stored?.excludeWeekends === "boolean" ? stored.excludeWeekends : DEFAULT_ANALYTICS_DAYS.excludeWeekends,
      excludeHolidays:
        typeof stored?.excludeHolidays === "boolean" ? stored.excludeHolidays : DEFAULT_ANALYTICS_DAYS.excludeHolidays,
    };
  } catch {
    return DEFAULT_ANALYTICS_DAYS;
  }
}

export function saveAnalyticsDays(days: AnalyticsDays): void {
  try {
    localStorage.setItem(DAYS_STORAGE_KEY, JSON.stringify(days));
  } catch {
    // Private window or blocked storage: the choice lasts for this page only.
  }
}

/** Same limits as the control plane's `user_filter` parameter. */
export const USER_FILTER_MAX_CONDITIONS = 8;
export const USER_FILTER_MAX_LENGTH = 2000;

/** Conditions on the stored access attributes, like a platform access rule without its mode. */
export interface AnalyticsUserFilterValue {
  combination: "all" | "any";
  conditions: PlatformAccessCondition[];
}

/** The `user_filter` query value; fixed key order, so equal filters reuse cached reads. */
export function userFilterParam(filter: AnalyticsUserFilterValue | null | undefined): string | undefined {
  if (!filter || filter.conditions.length === 0) return undefined;
  return JSON.stringify({
    combination: filter.combination,
    conditions: filter.conditions.map(({ claim, operator, value, case_sensitive }) => ({
      claim,
      operator,
      value,
      case_sensitive: case_sensitive ?? false,
    })),
  });
}

/** Without `days`, a read counts every day: for state counts such as storage or agents existing. */
export function kpiArgs(range: TimeRange, teamIds: string[] = [], userFilter?: string, days?: AnalyticsDays) {
  return {
    since: range.since,
    until: range.until,
    ...(teamIds.length > 0 && { teamIds }),
    ...(userFilter && { userFilter }),
    ...(days && { excludeWeekends: days.excludeWeekends, excludeHolidays: days.excludeHolidays }),
  };
}

/** For reads with calendar buckets or days: they follow the viewer's time zone. */
export function zonedKpiArgs(range: TimeRange, teamIds: string[] = [], userFilter?: string, days?: AnalyticsDays) {
  return { ...kpiArgs(range, teamIds, userFilter, days), tz: viewerTimeZone() };
}

/** Options for reads whose data carries no team: skipped under a team scope, which the tile says. */
export function platformOnly(teamIds: string[]) {
  return { ...KPI_CACHE, skip: teamIds.length > 0 };
}

/** True when every read of a tab failed: the control plane is unreachable, not one preset. */
export function allFailed(queries: { isError: boolean }[]): boolean {
  return queries.length > 0 && queries.every((q) => q.isError);
}
