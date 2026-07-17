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

// Part-renderer registry keyed by part `type` (#1977, RFC §9 item 1).
//
// Why this exists:
// - it is the ONE dispatch point for chat parts, replacing kind-switches
//   scattered across thread-rendering code (`linksOf`-style per-kind folds)
// - builtins (link, geo) and capability plugin parts resolve uniformly
// - a kind with no renderer is a SKIP at render time, never dropped data and
//   never a crash: `ThreadMessage` keeps the raw part regardless
//
// Duplicate kinds: the backend registry fails pod boot on a duplicate chat-part
// kind, so a collision here means the plugin index itself is wrong — the
// frontend mirror keeps the FIRST registration (builtins win) and warns.

import { builtinPartRenderers } from "./builtinPartRenderers";
import { capabilityUiPlugins } from "./index";
import type { CapabilityUiPlugin, UiPartRenderer } from "./types";

export function buildPartRendererRegistry(
  builtins: Record<string, UiPartRenderer> = builtinPartRenderers,
  plugins: readonly CapabilityUiPlugin[] = capabilityUiPlugins,
): ReadonlyMap<string, UiPartRenderer> {
  const registry = new Map<string, UiPartRenderer>(Object.entries(builtins));
  for (const plugin of plugins) {
    for (const [kind, renderer] of Object.entries(plugin.partRenderers ?? {})) {
      if (registry.has(kind)) {
        console.warn(
          `[capabilities] plugin "${plugin.id}" re-registers part kind "${kind}" — keeping the first registration`,
        );
        continue;
      }
      registry.set(kind, renderer);
    }
  }
  return registry;
}

const partRendererRegistry = buildPartRendererRegistry();

/** The renderer for a part kind, or undefined — undefined means skip. */
export function rendererForPartKind(kind: string): UiPartRenderer | undefined {
  return partRendererRegistry.get(kind);
}
