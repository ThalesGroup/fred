// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { resolvePreset, type TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import type {
  TraceCatalogSort,
  TraceConsentFilter,
  ListConversationTracesApiArg,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ANALYTICS_PRESETS } from "../AnalyticsPage/analyticsQuery";

export type OutcomeFilter = NonNullable<ListConversationTracesApiArg["outcomes"]>[number];
export type QuickStatus = "all" | "completed" | "failed";

export const quickOutcomes: Record<QuickStatus, OutcomeFilter[]> = {
  all: [],
  completed: ["completed"],
  failed: [
    "http_5xx",
    "http_429",
    "http_400",
    "http_other_4xx",
    "stream_interrupted",
    "timeout_or_connection",
    "context_limit",
    "tool_or_capability",
    "internal_or_unknown",
    "failed",
  ],
};
const quickStatuses = Object.keys(quickOutcomes) as QuickStatus[];
export const outcomes: OutcomeFilter[] = ["completed", ...quickOutcomes.failed, "in_progress", "paused", "unknown"];

export const traceRefreshIntervals = [0, 30, 60, 300, 900, 1800] as const;

export function readTraceRefresh(params: URLSearchParams) {
  return traceRefreshIntervals.find((interval) => String(interval) === params.get("refresh")) ?? 300;
}

export function quickStatus(selected: OutcomeFilter[]): QuickStatus | undefined {
  return quickStatuses.find((key) => {
    const preset = quickOutcomes[key];
    return preset.length === selected.length && preset.every((outcome) => selected.includes(outcome));
  });
}

const defaultPeriod = "last30d";
const consents: TraceConsentFilter[] = ["shared", "all", "masked"];
const sortFields: TraceCatalogSort[] = ["latest", "title", "user", "team", "outcome", "consent"];
export const defaultSort = { field: "latest", direction: "desc" } as const;

type CatalogFilters = {
  statusOutcomes: OutcomeFilter[];
  consent: TraceConsentFilter;
  teamIds: string[];
  period: TimeRange;
  sort: { field: TraceCatalogSort; direction: "asc" | "desc" };
};

function parsePeriod(params: URLSearchParams, openedAt: number): TimeRange {
  const presetKey = ANALYTICS_PRESETS.find((key) => key === params.get("period"));
  const offset = Number(params.get("offset"));
  const since = Date.parse(params.get("since") ?? "");
  const until = Date.parse(params.get("until") ?? "");
  if (since <= until) {
    const start = new Date(since).toISOString();
    const end = new Date(until).toISOString();
    if (start.length === 24 && end.length === 24 && !start.startsWith("0000")) {
      return {
        since: start,
        until: end,
        ...(presetKey && Number.isInteger(offset) && offset >= -1000 && offset < 0 ? { presetKey, offset } : {}),
      };
    }
  }
  return resolvePreset(presetKey ?? defaultPeriod, 0, new Date(openedAt));
}

export function readCatalogFilters(params: URLSearchParams, openedAt: number): CatalogFilters {
  const status = quickStatuses.find((key) => key === params.get("status")) ?? "failed";
  const requested = new Set(params.getAll("outcome"));
  const explicitOutcomes = outcomes.filter((outcome) => requested.has(outcome));
  return {
    statusOutcomes: explicitOutcomes.length ? explicitOutcomes : quickOutcomes[status],
    consent: consents.find((value) => value === params.get("consent")) ?? "shared",
    teamIds: [...new Set(params.getAll("team").filter((id) => id.trim() && id.length <= 255))].slice(0, 500),
    period: parsePeriod(params, openedAt),
    sort: {
      field: sortFields.find((field) => field === params.get("sort")) ?? defaultSort.field,
      direction: params.get("direction") === "asc" ? "asc" : defaultSort.direction,
    },
  };
}

export function writeCatalogFilters(params: URLSearchParams, filters: CatalogFilters): URLSearchParams {
  const { consent, period, sort, statusOutcomes, teamIds } = filters;
  const next = new URLSearchParams(params);
  for (const key of [
    "status",
    "outcome",
    "consent",
    "team",
    "period",
    "offset",
    "since",
    "until",
    "sort",
    "direction",
  ]) {
    next.delete(key);
  }
  const status = quickStatus(statusOutcomes);
  if (!status) statusOutcomes.forEach((outcome) => next.append("outcome", outcome));
  else if (status !== "failed") next.set("status", status);
  if (consent !== "shared") next.set("consent", consent);
  teamIds.forEach((id) => next.append("team", id));
  if (period.presetKey && (period.presetKey !== defaultPeriod || period.offset)) next.set("period", period.presetKey);
  if (period.offset) next.set("offset", String(period.offset));
  if (!period.presetKey || period.offset) {
    next.set("since", period.since);
    next.set("until", period.until);
  }
  if (sort.field !== defaultSort.field) next.set("sort", sort.field);
  if (sort.direction !== defaultSort.direction) next.set("direction", sort.direction);
  return next;
}
