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

// Pure view-model fold: ChatMessage stream → ThreadMessage rows.
// Extracted from useManagedChat so the fold is unit-testable (#1977) — it is
// the exact place chat parts used to be pre-folded lossily (links only) and
// must now retain every ui_part raw, unknown kinds included.

import type { ChatMessage, VectorSearchHit } from "../../../../slices/agentic/agenticOpenApi";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import type { RawUiPart } from "@rework/types/parts";
import type { ThreadMessage } from "@rework/types/thread";
import type { TokenUsage } from "@rework/types/conversation";
import { isTraceChannel, textOf, uiPartsOf } from "../../../utils/traceUtils";

// Raw shape of a persisted `HitlRequestPart` (fred-core `history_schema.py`).
// Hand-cast, matching this file's existing `RespPart` precedent: `agenticOpenApi.ts`
// has no live regeneration target (no `make update-*-api` target touches it — see
// `hitlResponseKey`'s docstring for the sibling case) and its `ChatMessage.parts`
// union predates these hitl part kinds, so a generated type isn't available here.
type ReqPart = {
  question?: string;
  choices?: Array<{ id: string; label: string }>;
  title?: string | null;
  stage?: string | null;
  free_text?: boolean;
  interrupt_id?: string | null;
  checkpoint_id?: string | null;
  pending_calls?: Array<{ tool_call_id?: string; tool_name?: string; args_preview?: string }>;
};

function hitlRequestPart(m: ChatMessage): ReqPart | undefined {
  return m.parts?.[0] as unknown as ReqPart | undefined;
}

// Groups messages by exchange_id, preserving first-appearance order — the exact
// grouping `toThreadMessages` folds over. Shared so `reconstructPendingHitl`
// (which needs only the LAST exchange) can never drift from that grouping.
function groupByExchange(messages: ChatMessage[]): { order: string[]; groups: Map<string, ChatMessage[]> } {
  const order: string[] = [];
  const groups = new Map<string, ChatMessage[]>();
  for (const msg of messages) {
    const eid = msg.exchange_id;
    if (!groups.has(eid)) {
      order.push(eid);
      groups.set(eid, []);
    }
    groups.get(eid)!.push(msg);
  }
  return { order, groups };
}

/**
 * Reconstructs the live `pendingHitl` state from persisted history, for the
 * "reload while a HITL gate is still open" case (#2286-ish — reported live:
 * refreshing the page while a confirmation was pending made the prompt vanish
 * and left the gated tool stuck showing "running").
 *
 * Why this is possible at all: the SSE stream that reaches an `awaiting_human`
 * pause ENDS there (the resume is a separate stream/call), so history — written
 * fire-and-forget right after the stream closes — already contains the
 * `hitl_request` row for a still-open gate by the time any refresh could race
 * it. The gap was purely that nothing reconstructed the interactive prompt
 * from it, AND (fixed alongside this) `HitlRequestPart` didn't persist the
 * resume identity (`interrupt_id`/`checkpoint_id`/`pending_calls`) needed to
 * actually answer it — only enough to display it read-only.
 *
 * Returns `null` when the last exchange's `hitl_request` (if any) already has
 * a matching `hitl_response` — i.e. nothing is actually still pending.
 */
export function reconstructPendingHitl(messages: ChatMessage[]): RuntimeAwaitingHumanEvent | null {
  const { order, groups } = groupByExchange(messages);
  const lastEid = order[order.length - 1];
  if (lastEid === undefined) return null;
  const lastMsgs = groups.get(lastEid)!;

  const hitlReqMsg = lastMsgs.find((m) => (m.channel as string) === "hitl_request");
  if (!hitlReqMsg) return null;
  const hasResponse = lastMsgs.some((m) => (m.channel as string) === "hitl_response");
  if (hasResponse) return null;

  const part = hitlRequestPart(hitlReqMsg);
  if (!part) return null;

  return {
    type: "awaiting_human",
    session_id: hitlReqMsg.session_id,
    exchange_id: lastEid,
    payload: {
      title: part.title ?? null,
      question: part.question ?? null,
      choices: part.choices ?? [],
      free_text: part.free_text ?? false,
      stage: part.stage ?? null,
      interrupt_id: part.interrupt_id ?? null,
      checkpoint_id: part.checkpoint_id ?? null,
      pending_calls: (part.pending_calls ?? []).map((c) => ({
        tool_call_id: c.tool_call_id ?? "",
        tool_name: c.tool_name ?? "",
        args_preview: c.args_preview ?? "",
      })),
    },
  };
}

/**
 * Maps a persisted HITL choice id (`HitlResponsePart.choice_id`) to an i18n key
 * for display in the chat, or `null` for an id this map doesn't know.
 *
 * Why this exists: the backend's `make_hitl_response` never populates `label`
 * (see `agent_app.py`'s history-persist path) — only the raw `choice_id`
 * ("proceed"/"cancel", the ONLY ids the tool-approval gate uses today) survives
 * into history, so without this the chat bubble showed the literal untranslated
 * id. This stays a plain function (not `useTranslation()`) because
 * `toThreadMessages` is a pure, hookless fold — the caller resolves the key via
 * `t()` at render time. An unrecognized id (e.g. a future bespoke Graph-authored
 * question) returns `null` so the caller can fall back to the raw text instead
 * of showing nothing.
 */
export function hitlResponseKey(choiceId: string): string | null {
  if (choiceId === "proceed") return "rework.hitlPrompt.accepted";
  if (choiceId === "cancel") return "rework.hitlPrompt.refused";
  return null;
}

export function toThreadMessages(messages: ChatMessage[], isStreaming: boolean): ThreadMessage[] {
  const { order, groups } = groupByExchange(messages);

  const result: ThreadMessage[] = [];
  const lastEid = order[order.length - 1] as string | undefined;

  for (const eid of order) {
    const msgs = groups.get(eid)!;
    const isLast = eid === lastEid;

    const userMsg = msgs.find((m) => m.role === "user" && (m.channel as string) !== "hitl_response");
    if (userMsg) {
      result.push({
        id: `${eid}:user`,
        role: "user",
        text: textOf(userMsg),
        isStreaming: false,
        traceMessages: [],
        sources: [],
        uiParts: [],
      });
    }

    const hitlReqMsg = msgs.find((m) => (m.channel as string) === "hitl_request");
    const hitlRespMsg = msgs.find((m) => (m.channel as string) === "hitl_response");
    // The trailing exchange's hitl_request with no matching response yet is a
    // GATE STILL OPEN, not history — `reconstructPendingHitl` turns it into the
    // live, interactive `pendingHitl` state instead (rendered by the caller at
    // the bottom of the thread, in the same spot a fresh live pause would be).
    // Rendering it here too would show it twice: once dead (this readonly
    // card), once actionable.
    const isOpenGate = isLast && !hitlRespMsg;
    if (hitlReqMsg && !isOpenGate) {
      const part = hitlRequestPart(hitlReqMsg);
      result.push({
        id: `${eid}:hitl_req`,
        role: "hitl_request",
        text: part?.question ?? "",
        isStreaming: false,
        traceMessages: [],
        sources: [],
        uiParts: [],
        hitlChoices: part?.choices ?? [],
        hitlTitle: part?.title,
      });
    }

    if (hitlRespMsg) {
      type RespPart = { label?: string | null; choice_id?: string };
      const part = hitlRespMsg.parts?.[0] as unknown as RespPart | undefined;
      result.push({
        id: `${eid}:hitl_resp`,
        role: "hitl_response",
        text: part?.label ?? part?.choice_id ?? "",
        isStreaming: false,
        traceMessages: [],
        sources: [],
        uiParts: [],
      });
    }

    const traceMessages = msgs.filter((m) => isTraceChannel(m.channel));
    const finalMessages = msgs.filter((m) => {
      const ch = m.channel as string;
      return m.role !== "user" && ch !== "hitl_request" && ch !== "hitl_response" && !isTraceChannel(m.channel);
    });

    if (traceMessages.length > 0 || finalMessages.length > 0 || (isStreaming && isLast)) {
      const sources: VectorSearchHit[] = [];
      let tokenUsage: TokenUsage | null = null;
      for (let i = finalMessages.length - 1; i >= 0; i--) {
        const meta = finalMessages[i].metadata as Record<string, unknown> | undefined;
        if (!tokenUsage && meta?.token_usage) {
          const tu = meta.token_usage as Record<string, number>;
          tokenUsage = {
            input_tokens: tu.input_tokens ?? 0,
            output_tokens: tu.output_tokens ?? 0,
            total_tokens: tu.total_tokens ?? 0,
          };
        }
        if (sources.length === 0) {
          const srcs = meta?.sources as VectorSearchHit[] | undefined;
          if (srcs && srcs.length > 0) sources.push(...srcs);
        }
        if (tokenUsage && sources.length > 0) break;
      }
      // Raw retention (#1977): every ui_part — link, geo, capability kinds,
      // and kinds this build does not know — survives into the view model.
      const uiParts: RawUiPart[] = finalMessages.flatMap((m) => uiPartsOf(m));
      result.push({
        id: `${eid}:assistant`,
        role: "assistant",
        text: finalMessages.map((m) => textOf(m)).join(""),
        isStreaming: isStreaming && isLast,
        traceMessages,
        sources,
        uiParts,
        tokenUsage,
      });
    }
  }

  return result;
}
