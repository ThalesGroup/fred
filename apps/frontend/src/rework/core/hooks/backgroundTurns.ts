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

// A streamed turn outlives the chat view that started it: leaving the
// conversation detaches it here instead of aborting it (the runtime cancels a
// turn whose stream closes), and the next view of that session adopts it back.
// Module-level on purpose, like sessionHistoryCache: the page remounts per agent.

import { useCallback, useSyncExternalStore, type SetStateAction } from "react";

import { forgetCachedSessionHistory } from "../../components/pages/ManagedChatPage/sessionHistoryCache";
import type { ChatMessage } from "../../../slices/runtime/runtimeOpenApi";
import type { ChatSseCallbacks } from "./useChatSse";

export type PendingMessage = { id: string; text: string; status: "waiting" | "offered" | "uncertain" };

export type ThoughtBuffer = {
  rank: number;
  text: string;
  phase: string;
  title: string | null | undefined;
  source: string | null | undefined;
};

/** The chat view currently rendering a turn. */
export type TurnHost = {
  read: () => ChatMessage[];
  write: (next: ChatMessage[]) => void;
  callbacks: () => ChatSseCallbacks;
  finish: (turn: LiveTurn) => void;
};

export type LiveTurn = {
  sessionId: string;
  /** Route of the conversation, so it can be opened from any page. */
  teamId: string;
  spaceId: string;
  agentInstanceId: string;
  controller: AbortController;
  steeringTurnId: string;
  thoughts: Map<string, ThoughtBuffer>;
  /** Null while detached; `messages` is then the turn's own copy of the thread. */
  host: TurnHost | null;
  messages: ChatMessage[];
  /** The turn ended on a question for the user (human input or interrupted run). */
  awaitingInput?: boolean;
  completed?: boolean;
  interrupted?: boolean;
  /** Session-keyed side effects that stay meaningful with no view attached. */
  detachedCallbacks: Pick<ChatSseCallbacks, "onTurnPersisted" | "onBackgroundTurnSettled">;
};

const INDICATOR_STORAGE_KEY = "chat.background-indicators";
const MAX_STORED_INDICATORS = 100;

function restoreIndicator(name: "awaitingInput" | "unread"): Set<string> {
  try {
    const ids: unknown = JSON.parse(sessionStorage.getItem(INDICATOR_STORAGE_KEY) ?? "null")?.[name];
    return new Set(
      Array.isArray(ids) ? ids.slice(-MAX_STORED_INDICATORS).filter((id): id is string => typeof id === "string") : [],
    );
  } catch {
    return new Set();
  }
}

const emptyQueue: PendingMessage[] = [];
const pendingQueues = new Map<string, PendingMessage[]>();
const detached = new Map<string, LiveTurn>();
// Every streaming turn, attached or not: what the sidebar shows and deletion cancels.
const running = new Map<string, LiveTurn>();
// Sessions whose last turn here stopped on a question; the next turn clears it.
const awaitingInput = restoreIndicator("awaitingInput");
// Sessions whose turn ended while no view showed it; opening one marks it read.
const unread = restoreIndicator("unread");
const runningListeners = new Set<() => void>();
const settledListeners = new Set<(turn: LiveTurn) => void>();

function notifyRunning(): void {
  for (const listener of runningListeners) listener();
}

function notifyIndicatorsChanged(): void {
  try {
    if (awaitingInput.size || unread.size) {
      sessionStorage.setItem(
        INDICATOR_STORAGE_KEY,
        JSON.stringify({
          awaitingInput: [...awaitingInput].slice(-MAX_STORED_INDICATORS),
          unread: [...unread].slice(-MAX_STORED_INDICATORS),
        }),
      );
    } else sessionStorage.removeItem(INDICATOR_STORAGE_KEY);
  } catch {
    // Storage may be blocked or full; the in-memory indicators still work.
  }
  notifyRunning();
}

function subscribeRunning(listener: () => void): () => void {
  runningListeners.add(listener);
  return () => runningListeners.delete(listener);
}

export function updatePendingMessages(sessionId: string, update: SetStateAction<PendingMessage[]>): void {
  const current = pendingQueues.get(sessionId) ?? emptyQueue;
  const next = typeof update === "function" ? update(current) : update;
  if (next === current) return;
  if (next.length) pendingQueues.set(sessionId, next);
  else pendingQueues.delete(sessionId);
  notifyRunning();
}

export function usePendingMessages(sessionId: string | null) {
  const messages = useSyncExternalStore(subscribeRunning, () =>
    sessionId ? (pendingQueues.get(sessionId) ?? emptyQueue) : emptyQueue,
  );
  const setMessages = useCallback(
    (update: SetStateAction<PendingMessage[]>) => {
      if (sessionId) updatePendingMessages(sessionId, update);
    },
    [sessionId],
  );
  return [messages, setMessages] as const;
}

export function setSessionAwaitingInput(sessionId: string, waiting: boolean): void {
  if (running.has(sessionId) || awaitingInput.has(sessionId) === waiting) return;
  if (waiting) awaitingInput.add(sessionId);
  else awaitingInput.delete(sessionId);
  notifyIndicatorsChanged();
}

export function registerTurn(turn: LiveTurn): void {
  running.set(turn.sessionId, turn);
  awaitingInput.delete(turn.sessionId);
  notifyIndicatorsChanged();
}

export type TurnStatus = "running" | "awaiting_input" | null;

/** Known only in this tab: the session list does not carry pending questions. */
export function useTurnStatus(sessionId: string): TurnStatus {
  return useSyncExternalStore(subscribeRunning, () =>
    running.has(sessionId) ? "running" : awaitingInput.has(sessionId) ? "awaiting_input" : null,
  );
}

/** Known only in this tab, like the turn status. */
export function useSessionUnread(sessionId: string): boolean {
  return useSyncExternalStore(subscribeRunning, () => unread.has(sessionId));
}

export function markSessionRead(sessionId: string): void {
  if (unread.delete(sessionId)) notifyIndicatorsChanged();
}

/** Notified when a turn ends while no view shows its conversation. */
export function subscribeBackgroundSettled(listener: (turn: LiveTurn) => void): () => void {
  settledListeners.add(listener);
  return () => settledListeners.delete(listener);
}

/**
 * Cancels the session's streaming turn and drops its cached thread. Called
 * before erasing a conversation: a running turn would write its history back.
 */
export function abortTurn(sessionId: string): void {
  updatePendingMessages(sessionId, []);
  running.get(sessionId)?.controller.abort();
  forgetCachedSessionHistory(sessionId);
  const cleared = awaitingInput.delete(sessionId);
  if (unread.delete(sessionId) || cleared) notifyIndicatorsChanged();
}

export function readTurnMessages(turn: LiveTurn): ChatMessage[] {
  return turn.host ? turn.host.read() : turn.messages;
}

export function writeTurnMessages(turn: LiveTurn, next: ChatMessage[]): void {
  if (turn.host) turn.host.write(next);
  else turn.messages = next;
}

/** The callbacks a turn event may fire right now. */
export function turnCallbacks(turn: LiveTurn): ChatSseCallbacks {
  return turn.host ? turn.host.callbacks() : turn.detachedCallbacks;
}

export function detachTurn(turn: LiveTurn): void {
  if (!turn.host) return;
  const { onTurnPersisted, onBackgroundTurnSettled } = turn.host.callbacks();
  turn.messages = turn.host.read();
  turn.detachedCallbacks = { onTurnPersisted, onBackgroundTurnSettled };
  turn.host = null;
  detached.set(turn.sessionId, turn);
}

/** Removes and returns the session's detached turn, if one is still streaming. */
export function takeDetachedTurn(sessionId: string): LiveTurn | undefined {
  const turn = detached.get(sessionId);
  detached.delete(sessionId);
  return turn;
}

/** Ends the turn on its view, or hands a detached turn's final thread to its owner. */
export function settleTurn(turn: LiveTurn): void {
  // A replacement turn of the same session may already be registered.
  if (running.get(turn.sessionId) === turn) {
    if (turn.interrupted || turn.controller.signal.aborted) updatePendingMessages(turn.sessionId, []);
    running.delete(turn.sessionId);
    if (turn.awaitingInput && !turn.interrupted && !turn.controller.signal.aborted) awaitingInput.add(turn.sessionId);
    notifyIndicatorsChanged();
  }
  if (turn.host) {
    turn.host.finish(turn);
    return;
  }
  if (detached.get(turn.sessionId) === turn) detached.delete(turn.sessionId);
  // Only deletion aborts a detached turn: its thread must not be cached again.
  if (!turn.controller.signal.aborted) {
    turn.detachedCallbacks.onBackgroundTurnSettled?.(turn.sessionId, turn.messages);
    if (turn.interrupted || (!turn.awaitingInput && !turn.completed)) return;
    unread.add(turn.sessionId);
    notifyIndicatorsChanged();
    for (const listener of settledListeners) listener(turn);
  }
}
