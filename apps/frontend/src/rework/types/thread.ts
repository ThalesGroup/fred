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

// View model for a single rendered exchange in the conversation thread.
// Carries raw API types (ChatMessage, VectorSearchHit) because the rendering
// layer (AssistantTurn, HitlPrompt) consumes them directly.

import type { ChatMessage, VectorSearchHit } from "../../slices/runtime/runtimeOpenApi";
import type { TokenUsage } from "./conversation";
import type { RawUiPart } from "./parts";

export interface ThreadMessage {
  id: string;
  role: "user" | "assistant" | "hitl_request" | "hitl_response";
  text: string;
  isStreaming: boolean;
  traceMessages: ChatMessage[];
  sources: VectorSearchHit[];
  /**
   * ALL chat parts produced by the agent (ui_parts: link, geo, capability
   * parts), carried RAW — never pre-folded per kind, which was lossy (#1977).
   * Rendering dispatches through the part-renderer registry; kinds without a
   * renderer are skipped visually but stay present here.
   */
  uiParts: RawUiPart[];
  /** Billed usage for the turn — every model call summed, which is what the
   *  provider charges and what the conversation header totals. A ReAct turn
   *  re-sends the whole context per call, so this legitimately counts the
   *  same history several times. */
  tokenUsage?: TokenUsage | null;
  /** Context size at the end of the turn (#2403) — the anchor the next turn
   *  subtracts from to work out what it genuinely added. */
  contextTokens?: number | null;
  /** What this turn actually ADDED: the new user message, the growth from its
   *  tool rounds, and the tokens it produced (#2403). This is what the
   *  per-message badge shows; null when the chain of `contextTokens` is
   *  broken (Graph agents, pre-#2403 history), where the badge falls back to
   *  `tokenUsage`. */
  marginalTokenUsage?: TokenUsage | null;
  hitlChoices?: Array<{ id: string; label: string }>;
  hitlTitle?: string | null;
}
