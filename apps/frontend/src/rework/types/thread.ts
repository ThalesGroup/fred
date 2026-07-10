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

import type { ChatMessage, VectorSearchHit } from "../../slices/agentic/agenticOpenApi";
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
  tokenUsage?: TokenUsage | null;
  hitlChoices?: Array<{ id: string; label: string }>;
  hitlTitle?: string | null;
}
