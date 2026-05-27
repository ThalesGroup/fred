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

// Transformation layer between runtime API types and the UI conversation model.
// No business logic here — only shape mapping. Keeps UI components free of
// knowledge about the wire format.

import type { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import type { VectorSearchHit } from "../../slices/runtime/runtimeOpenApi";
import type { Conversation, Message, MessageContent, Source, TraceMessage } from "../types/conversation.ts";
import { isFinalChannel, isTraceChannel, textOf } from "./traceUtils.ts";

// ── Source mapping ────────────────────────────────────────────────────────────

export function hitToSource(hit: VectorSearchHit, index: number): Source {
  const domain = hit.repository ?? hit.file_path?.split("/")[0] ?? "document";
  return {
    id: `${hit.uid}-${index}`,
    title: hit.title,
    domain,
    faviconUrl: undefined,
    url: hit.citation_url ?? hit.repo_url ?? undefined,
    restricted: hit.confidential ?? false,
    score: hit.score,
  };
}

// ── Message mapping ───────────────────────────────────────────────────────────

function contentFromChatMessage(msg: ChatMessage): MessageContent {
  const isStreaming = (msg.metadata?.extras as { streaming_delta?: boolean } | undefined)?.streaming_delta === true;
  if (isStreaming) {
    return { kind: "streaming", partial: textOf(msg) };
  }
  if (msg.channel === "error") {
    return { kind: "error", text: textOf(msg) };
  }
  return { kind: "text", text: textOf(msg) };
}

function traceFromMessages(msgs: ChatMessage[]): TraceMessage[] {
  return msgs
    .filter((m) => isTraceChannel(m.channel))
    .map((m, i) => ({
      id: `trace-${m.exchange_id ?? "x"}-${i}`,
      role: m.channel === "thought" || m.channel === "plan" ? ("thought" as const) : ("tool" as const),
      content: textOf(m),
      timestamp: m.timestamp ?? new Date().toISOString(),
    }));
}

// Groups a flat ChatMessage[] (one exchange) into a single UI Message.
// The exchange is identified by its exchange_id.
export function chatMessagesToMessage(exchangeMessages: ChatMessage[], parentId: string | null = null): Message | null {
  // Final message is the authoritative reply — take the highest-rank final.
  const finals = exchangeMessages
    .filter((m) => isFinalChannel(m.channel) && m.role === "assistant")
    .sort((a, b) => (b.rank ?? 0) - (a.rank ?? 0));

  const userMsg = exchangeMessages.find((m) => m.role === "user");
  const finalMsg = finals[0];

  if (!userMsg && !finalMsg) return null;

  // Prefer the user message as the authoritative source for the exchange ID.
  const id = userMsg?.exchange_id ?? finalMsg?.exchange_id ?? crypto.randomUUID();
  const timestamp = userMsg?.timestamp ?? finalMsg?.timestamp ?? new Date().toISOString();

  // Sources live on the final frame when the runtime attaches vector hits.
  const rawSources = (finalMsg as (ChatMessage & { sources?: VectorSearchHit[] }) | undefined)?.sources ?? [];
  const sources: Source[] = rawSources.map((h, i) => hitToSource(h, i));

  const role = userMsg ? "user" : "assistant";
  const primaryMsg = userMsg ?? finalMsg!;
  const content = contentFromChatMessage(primaryMsg);
  const trace = traceFromMessages(exchangeMessages);

  return {
    id,
    role,
    content,
    sources,
    trace,
    timestamp,
    parentId,
    childrenIds: [],
    activeChildId: null,
  };
}

// ── Conversation assembly ─────────────────────────────────────────────────────

// Groups a flat ChatMessage[] (all messages in a session) into a Conversation.
// Pairs user + assistant frames that share the same exchange_id.
export function buildConversation(sessionId: string, title: string, allMessages: ChatMessage[]): Conversation {
  const byExchange = new Map<string, ChatMessage[]>();
  for (const m of allMessages) {
    const key = m.exchange_id ?? m.session_id ?? "orphan";
    const group = byExchange.get(key) ?? [];
    group.push(m);
    byExchange.set(key, group);
  }

  const messages: Record<string, Message> = {};
  const rootMessageIds: string[] = [];

  for (const [, group] of byExchange) {
    // Build the user message first.
    const userMsgs = group.filter((m) => m.role === "user");
    const assistantMsgs = group.filter((m) => m.role === "assistant");

    if (userMsgs.length > 0) {
      const userUiMsg = chatMessagesToMessage(userMsgs, null);
      if (userUiMsg) {
        messages[userUiMsg.id] = userUiMsg;
        rootMessageIds.push(userUiMsg.id);

        if (assistantMsgs.length > 0) {
          const assistantUiMsg = chatMessagesToMessage(assistantMsgs, userUiMsg.id);
          if (assistantUiMsg) {
            // Give the assistant reply a non-colliding ID — user and assistant
            // share the same exchange_id so a suffix is needed to keep both
            // entries distinct in the messages Record.
            const replyId = `${assistantUiMsg.id}:reply`;
            const reply: Message = { ...assistantUiMsg, id: replyId };
            messages[replyId] = reply;
            userUiMsg.childrenIds.push(replyId);
            userUiMsg.activeChildId = replyId;
          }
        }
      }
    }
  }

  const now = new Date().toISOString();
  return {
    id: sessionId,
    title,
    createdAt: now,
    updatedAt: now,
    rootMessageIds,
    messages,
  };
}

// Walks the active branch of the message tree in display order.
export function activeThread(conversation: Conversation): Message[] {
  const result: Message[] = [];

  const visit = (id: string) => {
    const msg = conversation.messages[id];
    if (!msg) return;
    result.push(msg);
    if (msg.activeChildId) visit(msg.activeChildId);
  };

  for (const rootId of conversation.rootMessageIds) {
    visit(rootId);
  }

  return result;
}
