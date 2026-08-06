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

// The `options` slot is the per-pack config surface (e.g. the PowerPoint
// template upload): it must render only while the pack is active, so an
// inactive pack never mounts its options (whose effects would otherwise, for
// ppt_filler, register a Save-blocking "template required" error for a pack the
// user hasn't even turned on).

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ToolPack } from "../toolPacks";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { ToolPackCard } from "./ToolPackCard";

const pack: ToolPack = {
  id: "powerpoint_document",
  kind: "capabilities",
  icon: "slideshow",
  titleKey: "pack.title",
  descriptionKey: "pack.description",
  includes: [],
  enablesCapabilityIds: ["ppt_filler"],
};

function render(checked: boolean): string {
  return renderToStaticMarkup(
    <ToolPackCard
      pack={pack}
      checked={checked}
      disabled={false}
      availableIds={new Set(["ppt_filler"])}
      activeIds={new Set(checked ? ["ppt_filler"] : [])}
      onToggle={() => {}}
      options={<div data-testid="pack-options">options</div>}
    />,
  );
}

describe("ToolPackCard options slot", () => {
  it("renders the options only when the pack is active", () => {
    expect(render(false)).not.toContain("pack-options");
    expect(render(true)).toContain("pack-options");
  });
});
