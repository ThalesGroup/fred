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

// Config-widget registry keyed by capability id (RFC §9 item 4, #1903).
//
// Why this exists:
// - the exact mirror of `sidePanelRegistry` for the agent-creation form: a
//   capability config field whose `ui.widget` names a widget the OWNING
//   capability's plugin declares renders through that component instead of the
//   generic `TuningFieldRenderer`
// - unknown widget ids resolve to `undefined` and the caller falls back to the
//   generic renderer (forward-compatible, same policy as chat controls)

import { capabilityUiPlugins } from "./index";
import type { CapabilityConfigWidget, CapabilityUiPlugin } from "./types";

export function buildConfigWidgetRegistry(
  plugins: readonly CapabilityUiPlugin[] = capabilityUiPlugins,
): ReadonlyMap<string, ReadonlyMap<string, CapabilityConfigWidget>> {
  const registry = new Map<string, ReadonlyMap<string, CapabilityConfigWidget>>();
  for (const plugin of plugins) {
    const widgets = Object.entries(plugin.configWidgets ?? {});
    if (widgets.length === 0) continue;
    registry.set(plugin.id, new Map(widgets));
  }
  return registry;
}

const configWidgetRegistry = buildConfigWidgetRegistry();

/** Resolve one capability's config widget by `ui.widget` id, else undefined. */
export function configWidgetFor(
  capabilityId: string,
  widgetId: string | null | undefined,
  registry: ReadonlyMap<string, ReadonlyMap<string, CapabilityConfigWidget>> = configWidgetRegistry,
): CapabilityConfigWidget | undefined {
  if (!widgetId) return undefined;
  return registry.get(capabilityId)?.get(widgetId);
}
