// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type {
  AnalyticsCalendar,
  AnalyticsQuery,
  ConsumptionMeasure,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { consumptionQueries } from "./personalUsage";

/** An adjacent window of equal elapsed duration, including for a partial calendar period. */
export function previousPeriod(range: TimeRange): TimeRange {
  const since = Date.parse(range.since);
  return { since: new Date(since - (Date.parse(range.until) - since)).toISOString(), until: range.since };
}

export function collectiveConsumptionQueries(
  range: TimeRange,
  id: string,
  calendar: AnalyticsCalendar = {},
): AnalyticsQuery[] {
  const scope = { kind: "space", id } as const;
  const queries = consumptionQueries(range, scope).map((q) => ({ ...q, time: { ...q.time, calendar } }));
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
  const previous = consumptionQueries(previousPeriod(range), scope).map((q) => ({
    ...q,
    time: { ...q.time, calendar },
  }));
  return [
    ...queries,
    { ...previous[0], name: "previous_total" },
    { ...previous[4], name: "previous_impact" },
    {
      name: "conversations",
      scope,
      time: { since: range.since, until: range.until, timezone: "UTC", calendar },
      measures: ["activity.retained_conversations"],
    },
  ];
}

export function collectiveHistoryQueries(
  range: TimeRange,
  id: string,
  calendar: AnalyticsCalendar = {},
): AnalyticsQuery[] {
  const scope = { kind: "space", id } as const;
  const time = { since: range.since, until: range.until, timezone: "UTC", calendar } as const;
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
    ...periodQueries(range, id, calendar, "statistics", usageStatistics),
  ];
}

/** Source failures and a denied read must never become an empty chart. */
export function analyticsErrorKey(error: unknown): string {
  const status = error && typeof error === "object" && "status" in error ? error.status : undefined;
  if (status === 401 || status === 403 || status === 404) return "rework.teamAnalytics.denied";
  if (status === 422) return "rework.teamAnalytics.tooLarge";
  return "rework.teamAnalytics.unavailable";
}

export const usageStatistics: ConsumptionMeasure[] = [
  "activity.median_usage_days",
  "activity.median_days_per_week",
  "activity.mean_daily_active",
  "activity.daily_usage_share",
  "activity.median_turns_per_conversation",
  "activity.failure_rate",
  "activity.single_turn_rate",
];
export const creatorStatistics: ConsumptionMeasure[] = [
  "activity.retained_conversations",
  "activity.retained_conversations_per_creator_median",
  "activity.retained_conversations_top_decile_share",
  "activity.creators_1",
  "activity.creators_2_3",
  "activity.creators_4_10",
  "activity.creators_11_30",
  "activity.creators_31_plus",
];
export const inventoryMeasures: ConsumptionMeasure[] = [
  "inventory.enabled_agents",
  "inventory.retained_agents_created",
  "inventory.agents_published",
  "inventory.documents_added",
];
export const toolMeasures: ConsumptionMeasure[] = [
  "tools.attempts",
  "tools.successes",
  "tools.failures",
  "tools.cancelled",
  "tools.awaiting_human",
  "tools.failure_rate",
];
function periodQueries(
  range: TimeRange,
  id: string,
  calendar: AnalyticsCalendar,
  name: string,
  measures: ConsumptionMeasure[],
): AnalyticsQuery[] {
  const scope = { kind: "space", id } as const;
  return [range, previousPeriod(range)].map((period, i) => ({
    name: i ? `previous_${name}` : name,
    scope,
    measures,
    time: { since: period.since, until: period.until, timezone: "UTC", calendar },
  }));
}
export function collectiveInventoryQueries(
  range: TimeRange,
  id: string,
  calendar: AnalyticsCalendar = {},
): AnalyticsQuery[] {
  const inventory = periodQueries(range, id, calendar, "inventory", inventoryMeasures);
  // Enabled agents are a current stock, never a previous-period observation.
  inventory[1].measures = inventoryMeasures.filter((measure) => measure !== "inventory.enabled_agents");
  return [...inventory, ...periodQueries(range, id, calendar, "creators", creatorStatistics)];
}
export function collectiveToolQueries(
  range: TimeRange,
  id: string,
  calendar: AnalyticsCalendar = {},
): AnalyticsQuery[] {
  const queries = periodQueries(range, id, calendar, "tools", toolMeasures);
  return [...queries, { ...queries[0], name: "tool_ranking", group_by: ["tool"], limit: 100 }];
}
