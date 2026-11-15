// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import JSZip from "jszip";
import { expect, it } from "vitest";
import type { TFunction } from "i18next";
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
});
