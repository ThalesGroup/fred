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

// Pure UI types for the conversation domain.
// No imports from API slices — runtime types are transformed into these
// at the boundary (conversationUtils.ts).

export type SearchPolicy = "hybrid" | "strict" | "semantic";

export type RagScope = "all" | "library" | "file";

export type MessageRole = "user" | "assistant";

export interface Source {
  id: string;
  title: string;
  domain: string;
  faviconUrl?: string;
  url?: string;
  restricted: boolean;
  score?: number;
}

export interface TraceMessage {
  id: string;
  role: "tool" | "system" | "thought";
  content: string;
  timestamp: string;
}

// Discriminated union — add variants here as the UI supports new content types.
export type MessageContent =
  | { kind: "text"; text: string }
  | { kind: "error"; text: string }
  | { kind: "streaming"; partial: string };

export interface Message {
  id: string;
  role: MessageRole;
  content: MessageContent;
  sources: Source[];
  trace: TraceMessage[];
  timestamp: string;

  // Tree navigation — null means root / leaf.
  parentId: string | null;
  childrenIds: string[];
  activeChildId: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  // Ordered list of root-level message IDs (the visible thread spine).
  rootMessageIds: string[];
  // Flat map of all messages including branched alternatives.
  messages: Record<string, Message>;
}

export interface UserCapabilities {
  canDebug: boolean;
  canAdmin: boolean;
  canObservePlatform: boolean;
  canEditSessions: boolean;
  canDeleteSessions: boolean;
  /** True until `/frontend/bootstrap` has resolved at least once. `canAdmin`/
   * `canObservePlatform` default to `false` while this is true — callers that
   * gate access (e.g. `Protected`) must not treat that default as a denial. */
  isLoading: boolean;
}

export interface ConversationSettings {
  searchPolicy: SearchPolicy;
  ragScope: RagScope;
  /** IDs of libraries included in RAG scope when ragScope === "library". */
  selectedLibraryIds: string[];
  /** Agent instance ID driving this conversation. */
  agentInstanceId: string;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export const DEFAULT_CONVERSATION_SETTINGS: ConversationSettings = {
  searchPolicy: "hybrid",
  ragScope: "all",
  selectedLibraryIds: [],
  agentInstanceId: "",
};
