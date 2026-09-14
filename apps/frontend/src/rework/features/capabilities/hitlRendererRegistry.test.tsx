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
import { hitlRendererForTool } from "./hitlRendererRegistry";
import { capabilityUiPlugins } from "./index";
import type { CapabilityUiPlugin } from "./types";

const A = () => null;
const B = () => null;

describe("hitlRendererForTool", () => {
  it("resolves a renderer by the gated tool's name", () => {
    const plugins = [{ id: "x", hitlRenderers: { some_tool: A } }] as CapabilityUiPlugin[];
    const registry = new Map(Object.entries({ some_tool: A }));
    expect(hitlRendererForTool("some_tool", registry)).toBe(A);
    expect(plugins.length).toBe(1);
  });

  // A frontend build older than the pod meets tools it has never heard of on
  // every deploy. Absent is the correct answer, not a crash.
  it("returns nothing for a tool with no renderer, and for no tool at all", () => {
    expect(hitlRendererForTool("unknown_tool", new Map())).toBeUndefined();
    expect(hitlRendererForTool(undefined, new Map([["a", A]]))).toBeUndefined();
    expect(hitlRendererForTool(null, new Map([["a", B]]))).toBeUndefined();
  });

  it("wires the wiki's publish tool through the real plugin index", () => {
    // The registry is built from `capabilityUiPlugins` at module load, so this
    // is the end-to-end check that the plugin was actually registered.
    expect(hitlRendererForTool("wiki_publish_proposal")).toBeDefined();
    expect(capabilityUiPlugins.some((p) => p.id === "team_wiki")).toBe(true);
  });
});
