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
import {
  effectiveInventory,
  readOverrides,
  readTemplateSha,
  summarize,
  unmatchedOverrides,
  upsertOverride,
} from "./types";

function pattern(overrides: Partial<Pattern>): Pattern {
  return {
    id: "layout:0",
    source: "layout",
    source_index: 0,
    name: "Cover",
    label: "Cover",
    kind: "cover",
    included: true,
    ...overrides,
  };
}

const INVENTORY: TemplateInventory = {
  slide_width: 1,
  slide_height: 1,
  patterns: [
    pattern({}),
    pattern({ id: "slide:7", source: "slide", source_index: 7, label: "KPIs", kind: "figures" }),
    pattern({
      id: "slide:9",
      source: "slide",
      source_index: 9,
      label: "Chart",
      kind: "other",
      included: false,
      exclusion_reason: "chart",
    }),
  ],
};

describe("upsertOverride (the stored overrides shape)", () => {
  it("serialises only pattern_id, label, kind and included", () => {
    let overrides = upsertOverride([], "layout:0", { kind: "section" });
    expect(overrides).toEqual([{ pattern_id: "layout:0", kind: "section" }]);
    overrides = upsertOverride(overrides, "layout:0", { included: false });
    overrides = upsertOverride(overrides, "slide:7", { label: "Key figures" });
    expect(JSON.parse(JSON.stringify(overrides))).toEqual([
      { pattern_id: "layout:0", kind: "section", included: false },
      { pattern_id: "slide:7", label: "Key figures" },
    ]);
  });

  it("drops an override with no correction left", () => {
    let overrides = upsertOverride([{ pattern_id: "layout:0", kind: "section" }], "layout:0", { kind: null });
    expect(overrides).toEqual([]);
    overrides = upsertOverride([{ pattern_id: "slide:7", label: "x" }], "slide:7", { label: "  " });
    expect(overrides).toEqual([]);
  });
});

describe("effectiveInventory", () => {
  it("applies label, kind and inclusion without touching the source", () => {
    const effective = effectiveInventory(INVENTORY, [
      { pattern_id: "layout:0", label: "  Front page ", kind: "section", included: false },
      { pattern_id: "slide:9", included: true },
    ]);
    const [cover, kpis, chart] = effective.patterns ?? [];
    expect([cover.label, cover.kind, cover.included, cover.exclusion_reason]).toEqual([
      "Front page",
      "section",
      false,
      "author",
    ]);
    expect(kpis).toBe(INVENTORY.patterns?.[1]);
    expect([chart.included, chart.exclusion_reason]).toEqual([true, null]);
    expect(INVENTORY.patterns?.[0].label).toBe("Cover");
  });
});

describe("readers and summary", () => {
  it("counts usable and set-aside patterns", () => {
    expect(summarize(INVENTORY)).toEqual({ patterns: 2, excluded: 1 });
  });

  it("names the overrides a re-analysed template no longer matches", () => {
    expect(
      unmatchedOverrides(
        [
          { pattern_id: "layout:0", label: "x" },
          { pattern_id: "slide:404", included: false },
        ],
        INVENTORY,
      ),
    ).toEqual(["slide:404"]);
  });

  it("reads the stored config leniently", () => {
    expect(readOverrides({})).toEqual([]);
    expect(readOverrides({ overrides: "nope" })).toEqual([]);
    expect(readTemplateSha({ template_sha256: "" })).toBeNull();
    expect(readTemplateSha({ template_sha256: "abc" })).toBe("abc");
  });
});
