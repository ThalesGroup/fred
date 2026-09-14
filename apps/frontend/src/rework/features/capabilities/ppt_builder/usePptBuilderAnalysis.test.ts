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
import type { TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";
import { unmatchedOverrides } from "./usePptBuilderAnalysis";

const box = { x: 0, y: 0, w: 1, h: 1 };
const INVENTORY: TemplateInventory = {
  slide_width: 1,
  slide_height: 1,
  patterns: [
    {
      id: "layout:0",
      source: "layout",
      source_index: 0,
      name: "Cover",
      label: "Cover",
      intent: "title",
      zones: [{ key: "ph:0", role: "title", box }],
      groups: [
        {
          key: "sp:1",
          count: 1,
          item_zones: ["number"],
          item_keys: ["sp:1"],
          items: [[{ key: "sp:1/2", role: "number", box }]],
        },
      ],
      included: true,
      preferred: false,
      warnings: [],
    },
  ],
  shared_texts: [],
};

describe("unmatchedOverrides", () => {
  it("names the overrides a re-analysed template no longer matches", () => {
    expect(
      unmatchedOverrides(
        [
          { pattern_id: "layout:0", label: "x", zone_roles: { "ph:0": "keep", "sp:1/2": "label", "ph:9": "body" } },
          { pattern_id: "slide:404", included: false },
        ],
        INVENTORY,
      ),
    ).toEqual(["layout:0/ph:9", "slide:404"]);
  });
});
