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

// Capability-agnostic chat-turn-control fallback ("stock kit"), keyed by
// `widget` id alone (CAPAB-01 #1976, RFC §3.3). The MCP capability's widget
// ids (`attach_files`, `document_scope`, `search_policy`, `rag_scope`) are
// computed at prep by a single shared capability whose *id* is dynamic
// (`mcp:<server>`) — it cannot ship a plugin folder per server, so these rows
// resolve here instead of through `CapabilityUiPlugin.chatTurnControls`.
// `chatTurnControlRegistry.ts` only falls back to this map when no plugin
// claims the (capability_id, widget) pair.

import type { CapabilityChatTurnControl } from "../types";
import { AttachFilesControl } from "./AttachFilesControl";
import { DocumentScopeControl } from "./DocumentScopeControl";
import { RagScopeControl } from "./RagScopeControl";
import { SearchPolicyControl } from "./SearchPolicyControl";

export const stockChatTurnControlKit: Record<string, CapabilityChatTurnControl> = {
  attach_files: AttachFilesControl,
  document_scope: DocumentScopeControl,
  search_policy: SearchPolicyControl,
  rag_scope: RagScopeControl,
};
