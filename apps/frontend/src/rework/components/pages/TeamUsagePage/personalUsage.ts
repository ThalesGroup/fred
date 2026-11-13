// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type {
  AnalyticsQuery,
  AnalyticsResult,
  AnalyticsRow,
  AnalyticsScope,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";

export function personalQueries(range: TimeRange, organizationId: string, historical: boolean): AnalyticsQuery[] {
  const base = {
    scope: { kind: "self", organization_id: organizationId },
    time: { since: range.since, until: range.until, timezone: "UTC" },
  } as const;
  if (historical)
    return [
      {
        ...base,
        name: "skills",
        measures: ["skills.user_loads", "skills.agent_loads", "skills.total_loads"],
        group_by: ["skill"],
        limit: 100,
      },
    ];
  return consumptionQueries(range, base.scope);
}

export function consumptionQueries(range: TimeRange, scope: AnalyticsScope): AnalyticsQuery[] {
  const base = { scope, time: { since: range.since, until: range.until, timezone: "UTC" } } as const;
  return [
    {
      ...base,
      name: "total",
      measures: [
        "usage.input_tokens",
        "usage.output_tokens",
        "usage.total_tokens",
        "usage.cache_read_tokens",
        "usage.cache_creation_tokens",
      ],
    },
    { ...base, name: "series", measures: ["usage.total_tokens"], group_by: ["time"] },
    { ...base, name: "agents", measures: ["usage.total_tokens"], group_by: ["agent"], limit: 100 },
    { ...base, name: "models", measures: ["usage.total_tokens"], group_by: ["model"], limit: 100 },
    { ...base, name: "impact", measures: ["usage.cost_eur", "usage.co2e_grams", "usage.energy_kwh"] },
  ];
}

/** Chart libraries require numbers; never silently round an exact journal counter. */
export function chartInteger(value: string): number | undefined {
  if (!/^\d+$/.test(value)) return undefined;
  const n = Number(value);
  return Number.isSafeInteger(n) ? n : undefined;
}

export function dimension(row: AnalyticsRow) {
  const d = row.dimensions;
  switch (d.kind) {
    case "time":
      return { id: d.start, label: d.start };
    case "agent":
      return { id: `${d.space_id}/${d.agent_instance_id}`, label: d.display_name ?? d.agent_instance_id };
    case "model":
      return { id: JSON.stringify([d.model_source_id, d.upstream_model_id]), label: d.upstream_model_id };
    case "skill":
      return { id: d.name, label: d.name };
    default:
      return { id: "total", label: "total" };
  }
}

export function chartRows(result: AnalyticsResult | undefined) {
  const rows = (result?.rows ?? []).map((row) => ({
    ...dimension(row),
    value: chartInteger(row.values["usage.total_tokens"]),
    exact: row.values["usage.total_tokens"],
  }));
  return { overflow: rows.some((r) => r.value === undefined), rows };
}
