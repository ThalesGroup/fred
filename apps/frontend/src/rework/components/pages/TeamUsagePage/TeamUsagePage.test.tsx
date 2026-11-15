// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { AnalyticsResult } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  analyticsErrorKey,
  collectiveConsumptionQueries,
  collectiveHistoryQueries,
  previousPeriod,
} from "./teamAnalytics";
import TeamAnalytics from "./TeamAnalytics";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart", () => ({
  default: ({ rows }: { rows: unknown }) => <output>{JSON.stringify(rows)}</output>,
}));
const range = { since: "2026-03-29T00:00:00Z", until: "2026-03-30T00:00:00Z" };
const result = (values: Record<string, string>): AnalyticsResult => ({
  ...range,
  timezone: "UTC",
  measures: [],
  truncated: false,
  rows: [{ dimensions: { kind: "total" }, values }],
});
const state = { isLoading: false, isFetching: false, isError: false };
const data = {
  calculation: "exact" as const,
  collection_completeness: "unknown" as const,
  results: {
    turns: result({
      "activity.completed_turns": "9007199254740993",
      "activity.active_users": "0",
      "activity.observed_conversations": "0",
      "activity.failed_turns": "0",
      "activity.single_turn_conversations": "0",
    }),
  },
};

describe("Team analytics contracts", () => {
  it("keeps comparison duration exact through DST and all batches within server budgets", () => {
    expect(previousPeriod(range)).toEqual({ since: "2026-03-28T00:00:00.000Z", until: range.since });
    const sql = collectiveConsumptionQueries(range, "team");
    const history = collectiveHistoryQueries(range, "team");
    expect(sql).toHaveLength(8);
    expect(history).toHaveLength(5);
    for (const queries of [sql, history])
      for (const q of queries) {
        expect(q.scope).toEqual({ kind: "space", id: "team" });
        expect(q.time.timezone).toBe("UTC");
        expect(q.measures.length).toBeLessThanOrEqual(12);
        expect(q.limit ?? 100).toBeLessThanOrEqual(100);
        expect(q).not.toHaveProperty("user_id");
      }
    expect(sql.find((q) => q.name === "previous_total")?.time.until).toBe(range.since);
    expect(sql.find((q) => q.name === "agents")?.measures).toContain("usage.cost_eur");
    expect(history.find((q) => q.name === "turn_series")?.group_by).toEqual(["time"]);
  });
  it("distinguishes denied reads, source failures and exceeded budgets", () => {
    for (const status of [401, 403, 404]) expect(analyticsErrorKey({ status })).toBe("rework.teamAnalytics.denied");
    expect(analyticsErrorKey({ status: 503 })).toBe("rework.teamAnalytics.unavailable");
    expect(analyticsErrorKey({ status: 422 })).toBe("rework.teamAnalytics.tooLarge");
  });
  it("keeps exact integers and hides cached figures on a failed or refreshing read", () => {
    const ready = renderToStaticMarkup(
      <TeamAnalytics history={{ ...state, currentData: data }} consumption={state} agents={false} />,
    );
    expect(ready).toContain(BigInt("9007199254740993").toLocaleString());
    for (const error of [{ status: 403 }, { status: 503 }]) {
      const denied = renderToStaticMarkup(
        <TeamAnalytics
          history={{ ...state, currentData: data, isError: true, error }}
          consumption={state}
          agents={false}
        />,
      );
      expect(denied).toContain(analyticsErrorKey(error));
      expect(denied).not.toContain(BigInt("9007199254740993").toLocaleString());
    }
    const refreshing = renderToStaticMarkup(
      <TeamAnalytics history={{ ...state, currentData: data, isFetching: true }} consumption={state} agents={false} />,
    );
    expect(refreshing).toContain("common.loading");
    expect(refreshing).not.toContain(BigInt("9007199254740993").toLocaleString());
  });
  it("shows missing attribution as unavailable and retains the completed-turn count", () => {
    const currentData = { ...data, results: { turns: result({ "activity.completed_turns": "17" }) } };
    const html = renderToStaticMarkup(
      <TeamAnalytics history={{ ...state, currentData }} consumption={state} agents={false} />,
    );
    expect(html).toContain("17");
    expect(html).toContain("rework.teamAnalytics.unavailableValue");
    expect(html).not.toContain("session_id");
    expect(html).not.toContain("user_id");
  });
});
