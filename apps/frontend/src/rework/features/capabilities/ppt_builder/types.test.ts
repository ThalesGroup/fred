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

import { describe, expect, it } from "vitest";
import type { Pattern, TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";
import { allZones, effectiveInventory, readInventory, readOverrides, summarize, upsertOverride } from "./types";

const box = { x: 0, y: 0, w: 100, h: 100 };

function pattern(overrides: Partial<Pattern>): Pattern {
  return {
    id: "layout:0",
    source: "layout",
    source_index: 0,
    name: "Cover",
    label: "Cover",
    intent: "title",
    zones: [{ key: "ph:0", role: "title", box }],
    groups: [],
    included: true,
    preferred: false,
    warnings: [],
    ...overrides,
  };
}

const INVENTORY: TemplateInventory = {
  slide_width: 1,
  slide_height: 1,
  patterns: [
    pattern({}),
    pattern({
      id: "slide:7",
      source: "slide",
      source_index: 7,
      label: "KPIs",
      intent: "cards",
      zones: [{ key: "ph:0", role: "title", box }],
      groups: [
        {
          key: "sp:1",
          count: 2,
          item_zones: ["number", "label"],
          item_keys: ["sp:1", "sp:2"],
          items: [
            [
              { key: "sp:1/3", role: "number", box },
              { key: "sp:1/4", role: "label", box },
            ],
            [
              { key: "sp:2/5", role: "number", box },
              { key: "sp:2/6", role: "label", box },
            ],
          ],
        },
      ],
    }),
    pattern({
      id: "slide:9",
      source: "slide",
      source_index: 9,
      label: "Chart",
      intent: "content",
      included: false,
      exclusion_reason: "chart",
    }),
    pattern({ id: "layout:3", label: "Thanks", intent: "fixed", zones: [] }),
  ],
  shared_texts: [],
};

describe("upsertOverride", () => {
  it("creates, merges and drops an override that has nothing left", () => {
    let overrides = upsertOverride([], "layout:0", { intent: "section" });
    expect(overrides).toEqual([{ pattern_id: "layout:0", intent: "section" }]);
    overrides = upsertOverride(overrides, "layout:0", { zone_roles: { "ph:0": "keep" } });
    expect(overrides).toEqual([{ pattern_id: "layout:0", intent: "section", zone_roles: { "ph:0": "keep" } }]);
    overrides = upsertOverride(overrides, "layout:0", { intent: null, zone_roles: {} });
    expect(overrides).toEqual([{ pattern_id: "layout:0", intent: null, zone_roles: { "ph:0": "keep" } }]);
    overrides = upsertOverride([{ pattern_id: "layout:0", label: "x" }], "layout:0", { label: null });
    expect(overrides).toEqual([]);
  });
});

describe("effectiveInventory", () => {
  it("applies label, intent, inclusion and zone roles, group items included", () => {
    const effective = effectiveInventory(INVENTORY, [
      { pattern_id: "layout:0", label: "  Front page ", intent: "section", included: false },
      { pattern_id: "slide:7", zone_roles: { "sp:1/4": "keep" } },
      { pattern_id: "slide:9", included: true },
    ]);
    const [cover, kpis, chart] = effective.patterns;
    expect([cover.label, cover.intent, cover.included, cover.exclusion_reason]).toEqual([
      "Front page",
      "section",
      false,
      "author",
    ]);
    expect(kpis.groups[0].items[0][1].role).toBe("keep");
    expect(kpis.groups[0].item_zones).toEqual(["number", "keep"]);
    expect([chart.included, chart.exclusion_reason]).toEqual([true, null]);
    // The source is untouched.
    expect(INVENTORY.patterns[0].label).toBe("Cover");
  });
});

describe("summarize and readers", () => {
  it("counts usable, fixed and excluded patterns", () => {
    expect(summarize(INVENTORY)).toEqual({ patterns: 2, fixed: 1, excluded: 1 });
  });

  it("reads the stored config leniently", () => {
    expect(readOverrides({})).toEqual([]);
    expect(readOverrides({ overrides: "nope" })).toEqual([]);
    expect(readInventory({ inventory: null })).toBeNull();
    expect(readInventory({ inventory: INVENTORY })).toBe(INVENTORY);
  });

  it("lists group zones after the pattern's own, with their item index", () => {
    const zones = allZones(INVENTORY.patterns[1]);
    expect(zones.map((z) => [z.zone.key, z.item])).toEqual([
      ["ph:0", null],
      ["sp:1/3", 0],
      ["sp:1/4", 0],
      ["sp:2/5", 1],
      ["sp:2/6", 1],
    ]);
  });
});
