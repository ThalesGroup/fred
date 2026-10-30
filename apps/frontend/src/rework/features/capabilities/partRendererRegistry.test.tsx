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

// Part-renderer registry (#1977): uniform dispatch for builtin kinds (link,
// geo) and capability plugin kinds; unknown kinds resolve to undefined (skip).

import { describe, expect, it, vi } from "vitest";
import { buildPartRendererRegistry, latestPartPerObject, rendererForPartKind } from "./partRendererRegistry";
import type { CapabilityUiPlugin, UiPartIdentity, UiPartRendererProps } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (value: string) => value }),
}));

function Stub({ part }: UiPartRendererProps) {
  return <span>{part.type}</span>;
}

describe("partRendererRegistry (#1977)", () => {
  it("dispatches builtin kinds (link, geo) and plugin kinds uniformly", () => {
    const plugin: CapabilityUiPlugin = { id: "demo_echo", partRenderers: { demo_card: Stub } };
    const registry = buildPartRendererRegistry({ link: Stub, geo: Stub }, [plugin]);

    expect(registry.get("link")).toBe(Stub);
    expect(registry.get("geo")).toBe(Stub);
    expect(registry.get("demo_card")).toBe(Stub);
  });

  it("returns undefined for unknown kinds — the render-time skip signal", () => {
    const registry = buildPartRendererRegistry({ link: Stub }, []);
    expect(registry.get("part_kind_from_the_future")).toBeUndefined();
  });

  it("keeps the first registration and warns on a duplicate kind", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    function Second({ part }: UiPartRendererProps) {
      return <b>{part.type}</b>;
    }
    const dupBuiltin: CapabilityUiPlugin = { id: "rogue", partRenderers: { link: Second } };
    const dupPlugin: CapabilityUiPlugin = { id: "rogue2", partRenderers: { card: Second } };
    const first: CapabilityUiPlugin = { id: "first", partRenderers: { card: Stub } };

    const registry = buildPartRendererRegistry({ link: Stub }, [first, dupBuiltin, dupPlugin]);

    expect(registry.get("link")).toBe(Stub);
    expect(registry.get("card")).toBe(Stub);
    expect(warn).toHaveBeenCalledTimes(2);
    warn.mockRestore();
  });

  it("resolves the real plugin index: the frozen base parts are always present", () => {
    expect(rendererForPartKind("link")).toBeDefined();
    expect(rendererForPartKind("geo")).toBeDefined();
    expect(rendererForPartKind("nope")).toBeUndefined();
  });
});

describe("latestPartPerObject", () => {
  const byId = new Map<string, UiPartIdentity>([
    ["card", (part) => (typeof part.id === "string" ? part.id : undefined)],
  ]);

  it("keeps only the last version of an object, in place", () => {
    const v1 = { type: "card", id: "a", version: 1 };
    const other = { type: "card", id: "b", version: 1 };
    const v2 = { type: "card", id: "a", version: 2 };
    const geo = { type: "geo" };

    expect(latestPartPerObject([v1, other, geo, v2], byId)).toEqual([other, geo, v2]);
  });

  it("never merges parts without an identity, nor the same id across kinds", () => {
    const parts = [{ type: "geo" }, { type: "geo" }, { type: "card", id: "a" }, { type: "note", id: "a" }];
    expect(latestPartPerObject(parts, byId)).toEqual(parts);
  });

  it("merges the capability cards that update one object: deck, document, artifact", () => {
    const parts = [
      { type: "ppt_preview", preview_id: "deck", version: "1" },
      { type: "writable_document", document_id: "doc", updated_at: "1" },
      { type: "html_artifact", artifact_id: "art", version: "1" },
      { type: "ppt_preview", preview_id: "deck", version: "2" },
      { type: "writable_document", document_id: "doc", updated_at: "2" },
      { type: "html_artifact", artifact_id: "art", version: "2" },
    ];
    expect(latestPartPerObject(parts)).toEqual(parts.slice(3));
  });
});
