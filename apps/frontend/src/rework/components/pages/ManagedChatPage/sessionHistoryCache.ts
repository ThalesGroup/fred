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

import type { ChatMessage } from "../../../../slices/agentic/agenticOpenApi";

// In-memory per-session history cache backing instant conversation switches
// (#2239). Module-level ON PURPOSE: ManagedChatPage remounts with
// key={agentInstanceId} when switching agents, so hook/ref state would be
// lost exactly when the user hops between two agents' conversations — the
// case the cache exists for. Client-side only, per the History Ownership
// Contract (CHAT-UI-BACKLOG.md §0.4): the control-plane must never cache or
// serve message history, and the runtime stays the source of truth — every
// cached entry is revalidated against it on re-entry (useSessionHistory's
// serve-then-revalidate).
const MAX_CACHED_SESSIONS = 20;

// Map preserves insertion order; delete-then-set on every read and write
// keeps the FIRST key the least-recently-used one — a bounded LRU without a
// dedicated structure.
const cache = new Map<string, ChatMessage[]>();

export function getCachedSessionHistory(sessionId: string): ChatMessage[] | undefined {
  const entry = cache.get(sessionId);
  if (entry !== undefined) {
    cache.delete(sessionId);
    cache.set(sessionId, entry);
  }
  return entry;
}

export function setCachedSessionHistory(sessionId: string, messages: ChatMessage[]): void {
  cache.delete(sessionId);
  cache.set(sessionId, messages);
  while (cache.size > MAX_CACHED_SESSIONS) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
}

// Test-only: module-level state would otherwise leak between test cases.
export function clearSessionHistoryCache(): void {
  cache.clear();
}
