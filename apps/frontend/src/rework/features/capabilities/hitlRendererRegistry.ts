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

// Approval-card renderers keyed by gated tool name (WIKI-04, RFC §11).
//
// The third instance of the pattern `sidePanelRegistry` and
// `configWidgetRegistry` already use: plugins declare, one flat map resolves,
// an unknown key is simply absent rather than an error — a frontend older than
// the pod must never crash on a tool it has no renderer for.

import { capabilityUiPlugins } from "./index";
import type { CapabilityHitlRenderer, CapabilityUiPlugin } from "./types";

function buildRegistry(
  plugins: readonly CapabilityUiPlugin[] = capabilityUiPlugins,
): ReadonlyMap<string, CapabilityHitlRenderer> {
  const registry = new Map<string, CapabilityHitlRenderer>();
  for (const plugin of plugins) {
    for (const [toolName, Renderer] of Object.entries(plugin.hitlRenderers ?? {})) {
      // First wins, like the part-renderer registry: the backend already
      // refuses two capabilities exposing one tool name, so a collision here
      // means a stale build, not a decision to make at runtime.
      if (!registry.has(toolName)) registry.set(toolName, Renderer);
    }
  }
  return registry;
}

const hitlRendererRegistry = buildRegistry();

/** The approval-card renderer for this tool, or undefined when none exists. */
export function hitlRendererForTool(
  toolName: string | null | undefined,
  registry: ReadonlyMap<string, CapabilityHitlRenderer> = hitlRendererRegistry,
): CapabilityHitlRenderer | undefined {
  return toolName ? registry.get(toolName) : undefined;
}
