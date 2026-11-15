// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import JSZip from "jszip";
import { expect, it } from "vitest";
import type { TFunction } from "i18next";
import type { AnalyticsResponse } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { collectiveInventoryQueries } from "./teamAnalytics";
import { teamAnalyticsWorkbook } from "./exportTeamAnalytics";

it("preserves exact values, scope and period without formulas", async () => {
  const blob = await teamAnalyticsWorkbook(
    "team-a",
    [
      {
        calculation: "exact",
        collection_completeness: "unknown",
        results: {
          agents: {
            since: "2026-01-01T00:00:00Z",
            until: "2026-01-03T00:00:00Z",
            timezone: "UTC",
            calendar: { exclude_weekends: true, exclude_holidays: true },
            truncated: true,
            measures: [{ id: "activity.completed_turns", unit: "turn", calculation: "exact", value_type: "integer" }],
            rows: [
              {
                dimensions: {
                  kind: "agent",
                  space_id: "team-a",
                  agent_instance_id: "a",
                  display_name: '=HYPERLINK("secret") & <x>',
                },
                values: { "activity.completed_turns": "9007199254740993" },
              },
            ],
          },
        },
      },
    ],
    ((key: string) => (key === "rework.teamAnalytics.exportSheet" ? "Aggregates" : key)) as TFunction,
  );
  const zip = await JSZip.loadAsync(await blob.arrayBuffer());
  const xml = await zip.file("xl/worksheets/sheet1.xml")!.async("string");
  expect(xml).toContain("9007199254740993");
  expect(xml).toContain("team-a");
  expect(xml).toContain("2026-01-03T00:00:00Z");
  expect(xml).toContain("&amp; &lt;x&gt;");
  expect(xml).toContain('t="inlineStr"');
  expect(xml).not.toContain("<f>");
  expect(xml).toContain("FR national / UTC / L3133-1");
  expect(xml).toContain('r="R2" t="inlineStr"><is><t xml:space="preserve">true');
  expect(xml).toContain('r="S2" t="inlineStr"><is><t xml:space="preserve">true');
});

it("exports the enabled-agent stock only for the current inventory", async () => {
  const range = { since: "2026-01-01T00:00:00Z", until: "2026-01-04T00:00:00Z" };
  const queries = collectiveInventoryQueries(range, "team-a").filter((query) => query.name.endsWith("inventory"));
  expect(queries[0].measures).toContain("inventory.enabled_agents");
  expect(queries[1].measures).not.toContain("inventory.enabled_agents");
  const dataset: AnalyticsResponse = {
    calculation: "exact",
    collection_completeness: "unknown",
    results: Object.fromEntries(
      queries.map((query) => [
        query.name,
        {
          ...query.time,
          truncated: false,
          measures: query.measures.map((id) => ({ id, unit: "agent", calculation: "exact", value_type: "integer" })),
          rows: [{ dimensions: { kind: "total" }, values: Object.fromEntries(query.measures.map((id) => [id, "3"])) }],
        },
      ]),
    ),
  };
  const blob = await teamAnalyticsWorkbook("team-a", [dataset], ((key: string) => key) as TFunction);
  const zip = await JSZip.loadAsync(await blob.arrayBuffer());
  const xml = await zip.file("xl/worksheets/sheet1.xml")!.async("string");
  const rows = [...xml.matchAll(/<row\b[^>]*>.*?<\/row>/g)].map(([row]) => row);
  const stockRows = rows.filter((row) => row.includes("inventory.enabled_agents"));
  expect(stockRows).toHaveLength(1);
  expect(stockRows[0]).toContain(range.since);
  expect(stockRows[0]).not.toContain("previous_inventory");
  expect(
    rows.some((row) => row.includes("previous_inventory") && row.includes("inventory.retained_agents_created")),
  ).toBe(true);
});
