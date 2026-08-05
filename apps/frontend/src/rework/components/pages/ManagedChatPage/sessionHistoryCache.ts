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

// Per-session history cache backing instant conversation switches (#2239).
//
// Two layers, same bounded LRU semantics:
// - a module-level Map (the authority while the page lives) — module-level ON
//   PURPOSE: ManagedChatPage remounts with key={agentInstanceId} when
//   switching agents, so hook/ref state would be lost exactly when the user
//   hops between two agents' conversations;
// - a best-effort sessionStorage mirror, so the cache also survives a page
//   refresh (F5). sessionStorage — not localStorage — deliberately: it is
//   per-tab and cleared when the tab closes, the same lifetime already
//   accepted for `chat.composer.<sessionId>`, so conversation content never
//   outlives the user's tab on a shared machine. Every storage access is
//   wrapped: quota exhaustion or a blocked storage API degrades to
//   in-memory-only, never to an error.
//
// Client-side only, per the History Ownership Contract (CHAT-UI-BACKLOG.md
// §0.4): the control-plane must never cache or serve message history, and the
// runtime stays the source of truth — every cached entry is revalidated
// against it on re-entry (useSessionHistory's serve-then-revalidate).
const MAX_CACHED_SESSIONS = 20;
const STORAGE_PREFIX = "chat.history.";
const STORAGE_INDEX_KEY = "chat.history#index";

// Map preserves insertion order; delete-then-set on every read and write
// keeps the FIRST key the least-recently-used one — a bounded LRU without a
// dedicated structure.
const cache = new Map<string, ChatMessage[]>();

function setInMemory(sessionId: string, messages: ChatMessage[]): void {
  cache.delete(sessionId);
  cache.set(sessionId, messages);
  while (cache.size > MAX_CACHED_SESSIONS) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
}

// LRU order of the persisted entries, oldest first. Kept in its own key so
// eviction after a reload (when the in-memory Map is empty) still knows which
// persisted entry is oldest.
function storageReadIndex(): string[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_INDEX_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function storageWriteIndex(ids: string[]): void {
  try {
    sessionStorage.setItem(STORAGE_INDEX_KEY, JSON.stringify(ids));
  } catch {
    // Best-effort — the in-memory layer still works.
  }
}

function storageReadEntry(sessionId: string): ChatMessage[] | undefined {
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + sessionId);
    if (!raw) return undefined;
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ChatMessage[]) : undefined;
  } catch {
    return undefined;
  }
}

function storageDeleteEntry(sessionId: string): void {
  try {
    sessionStorage.removeItem(STORAGE_PREFIX + sessionId);
  } catch {
    // Best-effort.
  }
}

function storagePromote(sessionId: string): void {
  const ids = storageReadIndex();
  if (!ids.includes(sessionId)) return;
  storageWriteIndex([...ids.filter((id) => id !== sessionId), sessionId]);
}

function storagePersist(sessionId: string, messages: ChatMessage[]): void {
  let ids = storageReadIndex().filter((id) => id !== sessionId);
  ids.push(sessionId);
  while (ids.length > MAX_CACHED_SESSIONS) {
    storageDeleteEntry(ids.shift()!);
  }
  let payload: string;
  try {
    payload = JSON.stringify(messages);
  } catch {
    return; // Unserializable thread — in-memory only.
  }
  for (;;) {
    try {
      sessionStorage.setItem(STORAGE_PREFIX + sessionId, payload);
      break;
    } catch {
      // Quota (or storage blocked): evict the least-recently-used persisted
      // entry and retry; once nothing is left to evict, give up — the entry
      // stays served from memory for this page's lifetime.
      if (ids.length <= 1) {
        ids = ids.filter((id) => id !== sessionId);
        break;
      }
      storageDeleteEntry(ids.shift()!);
    }
  }
  storageWriteIndex(ids);
}

export function getCachedSessionHistory(sessionId: string): ChatMessage[] | undefined {
  const entry = cache.get(sessionId);
  if (entry !== undefined) {
    cache.delete(sessionId);
    cache.set(sessionId, entry);
    storagePromote(sessionId);
    return entry;
  }
  // Read-through: after a page refresh the Map starts empty but the tab's
  // sessionStorage doesn't — rehydrate so the conversation still renders
  // instantly (then revalidates) instead of blanking behind a spinner.
  const persisted = storageReadEntry(sessionId);
  if (persisted !== undefined) {
    setInMemory(sessionId, persisted);
    storagePromote(sessionId);
  }
  return persisted;
}

export function setCachedSessionHistory(sessionId: string, messages: ChatMessage[]): void {
  setInMemory(sessionId, messages);
  storagePersist(sessionId, messages);
}

// Clears BOTH layers. Used by tests for isolation; safe for future product
// use (e.g. a "clear local data" action).
export function clearSessionHistoryCache(): void {
  cache.clear();
  try {
    const doomed: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key && (key.startsWith(STORAGE_PREFIX) || key === STORAGE_INDEX_KEY)) doomed.push(key);
    }
    doomed.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    // Best-effort.
  }
}

// Test-only: simulates a page reload (JS heap gone, sessionStorage kept).
export function dropInMemorySessionHistoryForTests(): void {
  cache.clear();
}
