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

// Pure ChatMessage list helpers used by useChatSse.
// Kept in a separate file so they can be unit-tested without pulling in
// React, RTK Query, or Keycloak dependencies.

import type { ChatMessage } from "../../../slices/agentic/agenticOpenApi";

export const keyOf = (m: ChatMessage) => `${m.session_id}|${m.exchange_id}|${m.rank}|${m.role}|${m.channel}`;

export const exchangeKeyOf = (m: ChatMessage) => `${m.session_id}|${m.exchange_id}`;

export const stableConversationKeyOf = (m: ChatMessage) => `${exchangeKeyOf(m)}|${m.role}|${m.channel}`;

export const isOptimisticUserMessage = (m: ChatMessage) =>
  m.role === "user" &&
  m.channel === "final" &&
  (m.metadata?.extras as { optimistic_user?: unknown } | undefined)?.optimistic_user === true;

export const hasStreamingDeltaFlag = (m: ChatMessage) =>
  m.role === "assistant" &&
  m.channel === "final" &&
  (m.metadata?.extras as { streaming_delta?: unknown } | undefined)?.streaming_delta === true;

export const shouldClearStreamingDeltas = (m: ChatMessage) =>
  exchangeKeyOf(m) &&
  (m.channel === "tool_call" ||
    m.channel === "tool_result" ||
    (m.role === "assistant" && m.channel === "final" && !hasStreamingDeltaFlag(m)));

export const sortMessages = (arr: ChatMessage[]) =>
  [...arr].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank;
    const ta = a.timestamp ?? "";
    const tb = b.timestamp ?? "";
    return ta.localeCompare(tb);
  });

// Replace-or-insert one message, then keep the array sorted by (rank asc, timestamp asc).
// Streaming delta frames accumulate text onto the existing message rather than replacing it.
export const upsertOne = (all: ChatMessage[], m: ChatMessage): ChatMessage[] => {
  const exchangeKey = exchangeKeyOf(m);
  const base = shouldClearStreamingDeltas(m)
    ? all.filter((x) => !(exchangeKeyOf(x) === exchangeKey && hasStreamingDeltaFlag(x)))
    : all;
  const k = keyOf(m);
  const stableConversationKey = stableConversationKeyOf(m);
  const idx = base.findIndex((x) => {
    if (keyOf(x) === k) return true;
    if (isOptimisticUserMessage(x) && m.role === "user" && m.channel === "final") {
      return stableConversationKeyOf(x) === stableConversationKey;
    }
    return false;
  });
  if (idx >= 0) {
    const updated = [...base];
    if (hasStreamingDeltaFlag(m)) {
      const existing = updated[idx];
      const deltaText = (m.parts?.[0] as { type: string; text?: string } | undefined)?.text ?? "";
      const existingText = (existing.parts?.[0] as { type: string; text?: string } | undefined)?.text ?? "";
      updated[idx] = {
        ...m,
        parts: [{ type: "text" as const, text: existingText + deltaText }],
      };
    } else {
      updated[idx] = m;
    }
    return sortMessages(updated);
  }
  return sortMessages([...base, m]);
};
