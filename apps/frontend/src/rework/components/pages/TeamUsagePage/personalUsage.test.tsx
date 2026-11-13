// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import type { AnalyticsResponse } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import PersonalUsage from "./PersonalUsage";
import { chartInteger, chartRows, personalQueries } from "./personalUsage";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact";
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart", () => ({
  default: ({ rows }: { rows: unknown }) => <div>{JSON.stringify(rows)}</div>,
}));
vi.mock("@shared/molecules/BarChart/BarChart", () => ({
  default: ({ rows }: { rows: unknown }) => <div>{JSON.stringify(rows)}</div>,
}));
const range = { since: "2026-01-01T00:00:00Z", until: "2026-01-03T00:00:00Z" };
const response: AnalyticsResponse = {
  calculation: "mixed",
  collection_completeness: "unknown",
  results: {
    total: {
      ...range,
      timezone: "UTC",
      measures: [],
      truncated: false,
      rows: [{ dimensions: { kind: "total" }, values: { "usage.total_tokens": "123" } }],
    },
    series: {
      ...range,
      timezone: "UTC",
      measures: [],
      truncated: false,
      rows: [{ dimensions: { kind: "time", start: range.since }, values: { "usage.total_tokens": "123" } }],
    },
    agents: {
      ...range,
      timezone: "UTC",
      measures: [],
      truncated: true,
      rows: ["a", "b"].map((id) => ({
        dimensions: { kind: "agent", space_id: "space", agent_instance_id: id, display_name: "Same name" },
        values: { "usage.total_tokens": "10" },
      })),
    },
  },
};
const ready = { isError: false, isLoading: false, isFetching: false, currentData: response };
const failed = { ...ready, currentData: undefined, isError: true };
it("builds two separate self batches and controls chart integer conversion", () => {
  const sql = personalQueries(range, "Acme", false),
    history = personalQueries(range, "Acme", true);
  expect(sql).toHaveLength(5);
  expect(history).toHaveLength(1);
  for (const q of [...sql, ...history]) expect(q.scope).toEqual({ kind: "self", organization_id: "Acme" });
  expect(sql[4].measures).toEqual(["usage.cost_eur", "usage.co2e_grams", "usage.energy_kwh"]);
  expect(chartInteger("9007199254740991")).toBe(Number.MAX_SAFE_INTEGER);
  expect(chartInteger("9007199254740992")).toBeUndefined();
  expect(chartInteger("1.5")).toBeUndefined();
  const { rows } = chartRows(response.results.agents);
  expect(rows.map((r) => r.id)).toEqual(["space/a", "space/b"]);
  expect(rows.map((r) => r.label)).toEqual(["Same name", "Same name"]);
});
it("keeps SQL visible when history fails, with truncation and absent estimates", () => {
  const html = renderToStaticMarkup(<PersonalUsage organizationId="Acme" usage={ready} skills={failed} withSkills />);
  expect(html).toContain("value&quot;:123");
  expect(html).toContain("common.loadingError");
  expect(html).toContain("rework.personalAnalytics.truncated");
  expect(html).toContain("rework.tokenUsageImpact.unavailable");
});
it("keeps skills visible when SQL fails without rounding integers", () => {
  const skills = {
    ...ready,
    currentData: {
      ...response,
      results: {
        skills: {
          ...response.results.total,
          rows: [
            {
              dimensions: { kind: "skill" as const, name: "read-document" },
              values: {
                "skills.user_loads": "9007199254740993",
                "skills.agent_loads": "1",
                "skills.total_loads": "9007199254740994",
              },
            },
          ],
        },
      },
    },
  };
  const html = renderToStaticMarkup(<PersonalUsage organizationId="Acme" usage={failed} skills={skills} withSkills />);
  expect(html).toContain("read-document");
  expect(html).toContain("9,007,199,254,740,993");
  expect(html).toContain("common.loadingError");
});
it("renders overflowing counters exactly in the retained section", () => {
  const large = {
    ...ready,
    currentData: {
      ...response,
      results: {
        series: {
          ...response.results.series,
          rows: [
            {
              dimensions: { kind: "time" as const, start: range.since },
              values: { "usage.total_tokens": "9007199254740993" },
            },
          ],
        },
      },
    },
  };
  const html = renderToStaticMarkup(
    <PersonalUsage organizationId="Acme" usage={large} skills={failed} withSkills={false} />,
  );
  expect(html).toContain("9,007,199,254,740,993");
  expect(html).toContain("rework.personalAnalytics.chartOverflow");
});
it("hides previous-period data until currentData is ready", () => {
  const html = renderToStaticMarkup(
    <PersonalUsage
      organizationId="Acme"
      usage={{ ...ready, currentData: undefined, isFetching: true }}
      skills={failed}
      withSkills={false}
    />,
  );
  expect(html).not.toContain("Same name");
  expect(html).toContain("common.loading");
});
it("distinguishes missing, partial, zero, fallback and read error for shared impacts", () => {
  expect(renderToStaticMarkup(<TokenUsageImpact rows={[{}]} isLoading={false} />)).toContain(
    "rework.tokenUsageImpact.unavailable",
  );
  const html = renderToStaticMarkup(
    <TokenUsageImpact
      isLoading={false}
      estimates={{
        "usage.co2e_grams": { value: "0", coverage: "complete", fallback: false },
        "usage.energy_kwh": { value: "1.5", coverage: "partial", fallback: true },
        "usage.cost_eur": { value: null, coverage: "unavailable", fallback: false },
      }}
    />,
  );
  expect(html).toContain("0 g CO2e");
  expect(html).toContain("rework.tokenUsageImpact.partial");
  expect(html).toContain("rework.tokenUsageImpact.fallback");
  expect(renderToStaticMarkup(<TokenUsageImpact isLoading={false} isError />)).toContain("common.loadingError");
  expect(renderToStaticMarkup(<TokenUsageImpact rows={[{ co2e_grams: 1 }, {}]} isLoading={false} />)).toContain(
    "rework.tokenUsageImpact.partial",
  );
});

it("requires the shared working organization and never shows cached global data without it", () => {
  const html = renderToStaticMarkup(<PersonalUsage usage={ready} skills={ready} withSkills />);
  expect(html).toContain("rework.personalAnalytics.organizationRequired");
  expect(html).not.toContain("Same name");
  expect(html).not.toContain("value&quot;:123");
});
