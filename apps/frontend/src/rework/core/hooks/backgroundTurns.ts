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

import type { ChatMessage } from "../../../slices/runtime/runtimeOpenApi";
import type { ChatSseCallbacks } from "./useChatSse";

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
  controller: AbortController;
  steeringTurnId: string;
  thoughts: Map<string, ThoughtBuffer>;
  /** Null while detached; `messages` is then the turn's own copy of the thread. */
  host: TurnHost | null;
  messages: ChatMessage[];
  /** Session-keyed side effects that stay meaningful with no view attached. */
  detachedCallbacks: Pick<ChatSseCallbacks, "onTurnPersisted" | "onSessionTitle" | "onBackgroundTurnSettled">;
};

const detached = new Map<string, LiveTurn>();

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
  const { onTurnPersisted, onSessionTitle, onBackgroundTurnSettled } = turn.host.callbacks();
  turn.messages = turn.host.read();
  turn.detachedCallbacks = { onTurnPersisted, onSessionTitle, onBackgroundTurnSettled };
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
  if (turn.host) {
    turn.host.finish(turn);
    return;
  }
  if (detached.get(turn.sessionId) === turn) detached.delete(turn.sessionId);
  turn.detachedCallbacks.onBackgroundTurnSettled?.(turn.sessionId, turn.messages);
}
