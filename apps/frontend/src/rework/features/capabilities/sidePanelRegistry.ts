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

// Side-panel registry keyed by capability id (RFC §9 item 3).
//
// Why this exists:
// - it is the ONE resolution point for capability side panels, the exact mirror
//   of `partRendererRegistry` (item 1): the host asks which panels a session's
//   ACTIVE capabilities contribute and mounts them in the reserved right column
// - the plugin's `sidePanels` record IS the declaration — no backend descriptor
//   has to flow for a panel to appear; a capability with no plugin entry simply
//   contributes nothing (silent skip, never a crash)

import { capabilityUiPlugins } from "./index";
import type { CapabilityUiPlugin, CapabilitySidePanel } from "./types";

export interface SidePanelEntry {
  /** Owning capability id (`manifest.id`). */
  capabilityId: string;
  /** `SidePanelSpec.widget` id. */
  widget: string;
  /** The component to render in the right column. */
  Component: CapabilitySidePanel;
}

export function buildSidePanelRegistry(
  plugins: readonly CapabilityUiPlugin[] = capabilityUiPlugins,
): ReadonlyMap<string, readonly SidePanelEntry[]> {
  const registry = new Map<string, SidePanelEntry[]>();
  for (const plugin of plugins) {
    const panels = Object.entries(plugin.sidePanels ?? {});
    if (panels.length === 0) continue;
    registry.set(
      plugin.id,
      panels.map(([widget, Component]) => ({ capabilityId: plugin.id, widget, Component })),
    );
  }
  return registry;
}

const sidePanelRegistry = buildSidePanelRegistry();

/**
 * Every side panel contributed by the given active capabilities, in the order
 * the capabilities are supplied (then plugin declaration order). Capabilities
 * without side panels are skipped. Pure — safe to call on every render.
 */
export function sidePanelsForCapabilities(
  capabilityIds: readonly string[],
  registry: ReadonlyMap<string, readonly SidePanelEntry[]> = sidePanelRegistry,
): readonly SidePanelEntry[] {
  const entries: SidePanelEntry[] = [];
  for (const id of capabilityIds) {
    for (const entry of registry.get(id) ?? []) {
      entries.push(entry);
    }
  }
  return entries;
}
