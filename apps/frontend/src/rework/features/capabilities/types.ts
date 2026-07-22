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
import type { SearchPolicyName } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

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
 * A headless per-session capability probe (#1905 auto-open): mounted by the
 * chat page's side-panel host for every ACTIVE capability, whether or not its
 * panel is open. It renders nothing; it observes the opened conversation
 * (URL `?session=`, the rework convention) and dispatches capability signals —
 * e.g. writable_document requests its editor panel when the conversation
 * already has documents.
 */
export type CapabilitySessionProbe = ComponentType<{ capabilityId: string }>;

/**
 * A capability side panel (RFC §9 item 3) — mounted in the chat page's reserved
 * right column when its owning capability is active in the session.
 */
export type CapabilitySidePanel = ComponentType<CapabilitySidePanelProps>;

/** The RAG-scope closed set (RuntimeContext `search_rag_scope`, RFC §3.3). */
export type RagScopeName = "corpus_only" | "hybrid" | "general_only";

/**
 * Shared composer state threaded to every mounted chat-turn control (RFC §9
 * item 2). This is the same per-session state `SearchConfig` drove before its
 * rows were extracted into the stock kit (CAPAB-01 #1976) — the values keep
 * traveling to the pod exactly as before (`RuntimeContext` for the MCP stock
 * widgets today); `turn_options` is the generic per-capability path for other
 * capabilities, none of which are stock yet.
 */
export interface ChatTurnControlComposerState {
  /** Scopes the document/library picker's queries. */
  teamId: string;
  /** Opens the native file picker (composer attachment flow). */
  onAttach: () => void;
  selectedLibraryIds: string[];
  onSelectedLibraryIdsChange: (ids: string[]) => void;
  selectedDocumentUids: string[];
  onSelectedDocumentUidsChange: (uids: string[]) => void;
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange: (value: SearchPolicyName) => void;
  ragScope: RagScopeName;
  onRagScopeChange: (value: RagScopeName) => void;
}

export interface CapabilityChatTurnControlProps<TParams = Record<string, unknown>> {
  /** This control's resolved params (`ChatControlDescriptor.params`, RFC §3.3). */
  params: TParams;
  /** Shared composer state — see `ChatTurnControlComposerState`. */
  composer: ChatTurnControlComposerState;
  /** True when this control's own row/submenu is expanded. The host (the
   * composer control slot) tracks one open control at a time, exactly as the
   * former `SearchConfig`'s single `openMenu` state did. */
  open: boolean;
  /** Toggle this control's open state; the host closes any other open control. */
  onToggleOpen: () => void;
  /** Close the whole composer popover shell, e.g. after triggering an action. */
  onRequestClose?: () => void;
}

/**
 * A composer chat-turn control (RFC §9 item 2) — mounted in the composer
 * control slot for every `ChatControlDescriptor` the session's active
 * capabilities resolve to, in prep-returned order.
 */
export type CapabilityChatTurnControl<TParams = Record<string, unknown>> = ComponentType<
  CapabilityChatTurnControlProps<TParams>
>;

export interface CapabilityConfigWidgetProps {
  /** The capability this widget configures (`manifest.id`). */
  capabilityId: string;
  /** The team the agent is being created/edited for (scopes any lookups). */
  teamId?: string;
  disabled: boolean;
  /** This capability's current config values (the stored-config `config` object). */
  configValues: Record<string, unknown>;
  /** Patch one config value (same contract as `TuningFieldRenderer.onChange`). */
  onConfigChange: (key: string, value: unknown) => void;
  /** Pending asset files for this capability, keyed by `AssetSlot.key` (#1903). */
  assetFiles: Record<string, File | undefined>;
  /** Stage (or clear with `null`) one slot's file for the multipart save. */
  onAssetFileChange: (slotKey: string, file: File | null) => void;
  /**
   * Report a save-blocking problem for this capability (`null` = none). The
   * form disables Save while any ACTIVE capability reports one — how a widget
   * enforces e.g. "the template is mandatory" before the backend's 422.
   */
  onBlockingErrorChange: (message: string | null) => void;
}

/**
 * A custom agent-creation form widget (RFC §9 item 4, #1903) — rendered inside
 * the capability's card INSTEAD of the generic metadata-driven renderer, for
 * the config field(s) whose `ui.widget` names it.
 */
export type CapabilityConfigWidget = ComponentType<CapabilityConfigWidgetProps>;

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
  /**
   * Agent-creation form widgets keyed by `ui.widget` id (RFC §9 item 4,
   * #1903). A config field whose `ui.widget` resolves here renders through the
   * plugin widget; unknown ids fall back to the generic renderer.
   */
  configWidgets?: Record<string, CapabilityConfigWidget>;
  /**
   * Composer chat-turn controls keyed by `ChatControlDescriptor.widget` id
   * (RFC §9 item 2). Capabilities with dynamic ids (MCP servers, id = the
   * plain catalog server id) cannot each ship a plugin folder — they resolve
   * through the capability-agnostic stock kit fallback instead
   * (`chatTurnControlRegistry.ts`).
   */
  chatTurnControls?: Record<string, CapabilityChatTurnControl>;
  /**
   * Side panels keyed by `SidePanelSpec.widget` id (RFC §9 item 3). The host
   * mounts every panel a session's active capabilities declare, in the reserved
   * right column; unknown widget ids never occur here (the plugin IS the
   * declaration) but the host skips capabilities with no plugin entry.
   */
  sidePanels?: Record<string, CapabilitySidePanel>;
  /**
   * Headless session probes (#1905 auto-open), mounted by the side-panel host
   * for every ACTIVE capability whether or not its panel is open. The one
   * plugin path for "observe the opened conversation and react" behaviours —
   * e.g. writable_document auto-opens its editor when the conversation already
   * has documents (its card renderer only covers live writes, not replay).
   */
  sessionProbes?: readonly CapabilitySessionProbe[];
}
