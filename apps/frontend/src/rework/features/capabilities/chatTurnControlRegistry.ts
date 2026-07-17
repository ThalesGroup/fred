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

// Chat-turn-control registry keyed by capability id, with a capability-agnostic
// "stock kit" fallback keyed by widget id alone (CAPAB-01 #1976, RFC §9 item
// 2). The exact mirror of `sidePanelRegistry` (RFC §9 item 3), plus one wrinkle:
// MCP capabilities have DYNAMIC ids (the plain catalog server id) and cannot
// each ship a plugin folder, so their stock widgets (`attach_files`,
// `document_scope`, `search_policy`, `rag_scope`) resolve through the stock
// kit instead of a per-capability plugin entry.
//
// Resolution order per descriptor: the owning capability's own plugin entry
// first (a capability MAY override a stock widget id), then the stock kit by
// widget id; neither found is a silent skip — same forward-compatibility rule
// as part renderers and side panels (a frontend build older than a pod must
// never crash on a new widget id).

import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { capabilityUiPlugins } from "./index";
import { stockChatTurnControlKit } from "./stockKit";
import type { CapabilityChatTurnControl, CapabilityUiPlugin } from "./types";

export interface ChatTurnControlRegistry {
  /** Plugin-declared controls, keyed by capability id then widget id. */
  byCapability: ReadonlyMap<string, Record<string, CapabilityChatTurnControl>>;
  /** Capability-agnostic fallback, keyed by widget id alone. */
  stockKit: Record<string, CapabilityChatTurnControl>;
}

export interface ResolvedChatTurnControl {
  /** Owning capability id (`ChatControlDescriptor.capability_id`). */
  capabilityId: string;
  /** `ChatControlDescriptor.widget` id. */
  widget: string;
  /** `ChatControlDescriptor.params`, defaulted to `{}` when omitted. */
  params: Record<string, unknown>;
  /** The component to mount in the composer control slot. */
  Component: CapabilityChatTurnControl;
}

export function buildChatTurnControlRegistry(
  plugins: readonly CapabilityUiPlugin[] = capabilityUiPlugins,
  stockKit: Record<string, CapabilityChatTurnControl> = stockChatTurnControlKit,
): ChatTurnControlRegistry {
  const byCapability = new Map<string, Record<string, CapabilityChatTurnControl>>();
  for (const plugin of plugins) {
    if (plugin.chatTurnControls) byCapability.set(plugin.id, plugin.chatTurnControls);
  }
  return { byCapability, stockKit };
}

const chatTurnControlRegistry = buildChatTurnControlRegistry();

/**
 * Resolve every mountable chat-turn control for the given (already-ordered)
 * descriptors, in list order. A descriptor whose (capability_id, widget) pair
 * resolves to neither a plugin entry nor the stock kit is skipped — never a
 * crash. Pure — safe to call on every render.
 */
export function resolveChatTurnControls(
  descriptors: readonly ChatControlDescriptor[],
  registry: ChatTurnControlRegistry = chatTurnControlRegistry,
): readonly ResolvedChatTurnControl[] {
  const resolved: ResolvedChatTurnControl[] = [];
  for (const descriptor of descriptors) {
    const Component =
      registry.byCapability.get(descriptor.capability_id)?.[descriptor.widget] ?? registry.stockKit[descriptor.widget];
    if (!Component) continue;
    resolved.push({
      capabilityId: descriptor.capability_id,
      widget: descriptor.widget,
      params: (descriptor.params as Record<string, unknown> | undefined) ?? {},
      Component,
    });
  }
  return resolved;
}
