// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { AnalyticsQuery } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { consumptionQueries } from "./personalUsage";

/** An adjacent window of equal elapsed duration, including for a partial calendar period. */
export function previousPeriod(range: TimeRange): TimeRange {
  const since = Date.parse(range.since);
  return { since: new Date(since - (Date.parse(range.until) - since)).toISOString(), until: range.since };
}

export function collectiveConsumptionQueries(range: TimeRange, id: string): AnalyticsQuery[] {
  const scope = { kind: "space", id } as const;
  const queries = consumptionQueries(range, scope);
  for (const query of queries) {
    if (query.name === "agents" || query.name === "models")
      query.measures = [
        "usage.total_tokens",
        "usage.input_tokens",
        "usage.output_tokens",
        "usage.cost_eur",
        "usage.co2e_grams",
        "usage.energy_kwh",
      ];
  }
  const previous = consumptionQueries(previousPeriod(range), scope);
  return [
    ...queries,
    { ...previous[0], name: "previous_total" },
    { ...previous[4], name: "previous_impact" },
    {
      name: "conversations",
      scope,
      time: { since: range.since, until: range.until, timezone: "UTC" },
      measures: ["activity.retained_conversations"],
    },
  ];
}

export function collectiveHistoryQueries(range: TimeRange, id: string): AnalyticsQuery[] {
  const scope = { kind: "space", id } as const;
  const time = { since: range.since, until: range.until, timezone: "UTC" } as const;
  const previous = previousPeriod(range);
  return [
    {
      name: "turns",
      scope,
      time,
      measures: [
        "activity.completed_turns",
        "activity.agents_used",
        "activity.active_users",
        "activity.observed_conversations",
        "activity.failed_turns",
        "activity.single_turn_conversations",
      ],
    },
    {
      name: "previous_turns",
      scope,
      time: { ...time, ...previous },
      measures: [
        "activity.completed_turns",
        "activity.agents_used",
        "activity.active_users",
        "activity.observed_conversations",
        "activity.failed_turns",
        "activity.single_turn_conversations",
      ],
    },
    { name: "turn_series", scope, time, measures: ["activity.completed_turns"], group_by: ["time"] },
    { name: "turn_agents", scope, time, measures: ["activity.completed_turns"], group_by: ["agent"], limit: 100 },
    {
      name: "skills",
      scope,
      time,
      measures: ["skills.user_loads", "skills.agent_loads", "skills.total_loads"],
      group_by: ["skill"],
      limit: 100,
    },
  ];
}

/** Source failures and a denied read must never become an empty chart. */
export function analyticsErrorKey(error: unknown): string {
  const status = error && typeof error === "object" && "status" in error ? error.status : undefined;
  if (status === 401 || status === 403 || status === 404) return "rework.teamAnalytics.denied";
  if (status === 422) return "rework.teamAnalytics.tooLarge";
  return "rework.teamAnalytics.unavailable";
}
