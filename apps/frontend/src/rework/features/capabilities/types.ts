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

// Capability UI plugin contract (AGENT-CAPABILITY-RFC §9).
//
// One plugin object per capability, one shared registration edit (index.ts).
// The frontend mirror of the backend capability registry: each record key is
// resolved by its host slot at render time; unknown keys/kinds are silently
// skipped so a frontend build older than a pod never crashes on new parts.

import type { ComponentType } from "react";
import type { RawUiPart } from "@rework/types/parts";

export interface UiPartRendererProps {
  /** The raw part; renderers narrow it to their generated type. */
  part: RawUiPart;
}

/** Renders ONE chat part of the kind it is registered under. */
export type UiPartRenderer = ComponentType<UiPartRendererProps>;

export interface CapabilitySidePanelProps {
  /** The capability this panel belongs to (`manifest.id`). */
  capabilityId: string;
  /** Close the side-panel column (host owns open state). */
  onClose: () => void;
}

/**
 * A capability side panel (RFC §9 item 3) — mounted in the chat page's reserved
 * right column when its owning capability is active in the session.
 */
export type CapabilitySidePanel = ComponentType<CapabilitySidePanelProps>;

export interface CapabilityUiPlugin {
  /** Backend capability id (`manifest.id`), e.g. "demo_echo". */
  id: string;
  /**
   * Chat-part renderers keyed by part `type` (#1977). Keys must not collide
   * with builtin kinds (link, geo) or another plugin — the backend registry
   * fails pod boot on duplicate kinds; the frontend mirror keeps first-wins
   * and warns.
   */
  partRenderers?: Record<string, UiPartRenderer>;
  /** Agent-creation form widgets keyed by `ui.widget` id (typed by its host slice, RFC §9 item 4). */
  configWidgets?: Record<string, unknown>;
  /** Composer chat-turn controls keyed by widget id (typed by its host slice, RFC §9 item 2). */
  chatTurnControls?: Record<string, unknown>;
  /**
   * Side panels keyed by `SidePanelSpec.widget` id (RFC §9 item 3). The host
   * mounts every panel a session's active capabilities declare, in the reserved
   * right column; unknown widget ids never occur here (the plugin IS the
   * declaration) but the host skips capabilities with no plugin entry.
   */
  sidePanels?: Record<string, CapabilitySidePanel>;
}
