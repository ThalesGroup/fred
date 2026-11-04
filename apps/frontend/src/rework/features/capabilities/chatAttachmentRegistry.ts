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

// Chat-attachment handler registry keyed by capability id - the mirror of
// `hitlRendererRegistry`: the chat asks which handlers a session's ACTIVE
// capabilities contribute and calls them for each attached file. A capability
// with no handler contributes nothing (silent skip, never a crash).

import { capabilityUiPlugins } from "./index";
import type { CapabilityChatAttachmentHandler, CapabilityUiPlugin } from "./types";

export interface ChatAttachmentHandlerEntry {
  /** Owning capability id (`manifest.id`). */
  capabilityId: string;
  handle: CapabilityChatAttachmentHandler;
}

export function buildChatAttachmentRegistry(
  plugins: readonly CapabilityUiPlugin[] = capabilityUiPlugins,
): ReadonlyMap<string, ChatAttachmentHandlerEntry> {
  const registry = new Map<string, ChatAttachmentHandlerEntry>();
  for (const plugin of plugins) {
    if (plugin.onChatAttachment) {
      registry.set(plugin.id, { capabilityId: plugin.id, handle: plugin.onChatAttachment });
    }
  }
  return registry;
}

const chatAttachmentRegistry = buildChatAttachmentRegistry();

/** The attachment handlers of the given active capabilities, in the order supplied. Pure. */
export function chatAttachmentHandlersForCapabilities(
  capabilityIds: readonly string[],
  registry: ReadonlyMap<string, ChatAttachmentHandlerEntry> = chatAttachmentRegistry,
): readonly ChatAttachmentHandlerEntry[] {
  return capabilityIds.flatMap((id) => {
    const entry = registry.get(id);
    return entry ? [entry] : [];
  });
}
