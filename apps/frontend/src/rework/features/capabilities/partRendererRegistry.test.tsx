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
import { buildPartRendererRegistry, rendererForPartKind } from "./partRendererRegistry";
import type { CapabilityUiPlugin, UiPartRendererProps } from "./types";

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

  it("resolves the real plugin index: demo_echo contributes demo_card", () => {
    expect(rendererForPartKind("demo_card")).toBeDefined();
    expect(rendererForPartKind("link")).toBeDefined();
    expect(rendererForPartKind("geo")).toBeDefined();
    expect(rendererForPartKind("nope")).toBeUndefined();
  });
});
