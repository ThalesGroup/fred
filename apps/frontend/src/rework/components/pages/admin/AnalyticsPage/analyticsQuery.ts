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

export function kpiArgs(range: TimeRange, teamIds: string[] = [], userFilter?: string) {
  return {
    since: range.since,
    until: range.until,
    ...(teamIds.length > 0 && { teamIds }),
    ...(userFilter && { userFilter }),
  };
}

/** For reads with calendar buckets or days: they follow the viewer's time zone. */
export function zonedKpiArgs(range: TimeRange, teamIds: string[] = [], userFilter?: string) {
  return { ...kpiArgs(range, teamIds, userFilter), tz: viewerTimeZone() };
}

/** Options for reads whose data carries no team: skipped under a team scope, which the tile says. */
export function platformOnly(teamIds: string[]) {
  return { ...KPI_CACHE, skip: teamIds.length > 0 };
}

/** True when every read of a tab failed: the control plane is unreachable, not one preset. */
export function allFailed(queries: { isError: boolean }[]): boolean {
  return queries.length > 0 && queries.every((q) => q.isError);
}
