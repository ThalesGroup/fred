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

// Side-panel registry (#1979): a session's active capabilities resolve to the
// panels their plugins declare; capabilities with no panel are skipped.

import { describe, expect, it } from "vitest";
import { buildSidePanelRegistry, sidePanelsForCapabilities } from "./sidePanelRegistry";
import type { CapabilitySidePanelProps, CapabilityUiPlugin } from "./types";

function StubPanel(_props: CapabilitySidePanelProps) {
  return <div />;
}

describe("sidePanelRegistry (#1979)", () => {
  const withPanel: CapabilityUiPlugin = { id: "demo_echo", sidePanels: { demo_notes: StubPanel } };
  const withoutPanel: CapabilityUiPlugin = { id: "plain", partRenderers: {} };

  it("resolves the panels an active capability contributes", () => {
    const registry = buildSidePanelRegistry([withPanel, withoutPanel]);
    const entries = sidePanelsForCapabilities(["demo_echo"], registry);

    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ capabilityId: "demo_echo", widget: "demo_notes", Component: StubPanel });
  });

  it("skips capabilities that declare no side panel", () => {
    const registry = buildSidePanelRegistry([withPanel, withoutPanel]);
    expect(sidePanelsForCapabilities(["plain"], registry)).toHaveLength(0);
  });

  it("skips capability ids with no registered plugin (silent, never a crash)", () => {
    const registry = buildSidePanelRegistry([withPanel]);
    expect(sidePanelsForCapabilities(["not_installed"], registry)).toHaveLength(0);
  });

  it("preserves the order the capabilities are supplied", () => {
    const other: CapabilityUiPlugin = { id: "other", sidePanels: { other_panel: StubPanel } };
    const registry = buildSidePanelRegistry([withPanel, other]);
    const entries = sidePanelsForCapabilities(["other", "demo_echo"], registry);

    expect(entries.map((e) => e.capabilityId)).toEqual(["other", "demo_echo"]);
  });
});
