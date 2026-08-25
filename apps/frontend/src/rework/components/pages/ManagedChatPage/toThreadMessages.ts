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

import type {
  ChatMessage,
  HitlRequestPart,
  HitlResponsePart,
  VectorSearchHit,
} from "../../../../slices/runtime/runtimeOpenApi";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import type { RawUiPart } from "@rework/types/parts";
import type { ThreadMessage } from "@rework/types/thread";
import type { TokenUsage } from "@rework/types/conversation";
import { isTraceChannel, textOf, uiPartsOf } from "../../../utils/traceUtils";

function hitlRequestPart(m: ChatMessage): HitlRequestPart | undefined {
  return m.parts?.[0] as HitlRequestPart | undefined;
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

/**
 * What a turn genuinely ADDED, as opposed to what it was billed (#2403).
 *
 * Within a conversation the context only grows, so a turn's new input is the
 * context it ends with minus the context the PREVIOUS turn ended with. That
 * span covers the previous answer as it is re-sent, the new question, and the
 * growth from this turn's tool rounds. Everything else in the billed figure is
 * older history being re-sent — real cost, shown in the header, but not new.
 *
 * The anchor is the previous `contextTokens` ALONE — deliberately not
 * `+ output(T-1)`. Adding the previous turn's output assumes all of it comes
 * back in the next prompt, and it does not: reasoning tokens are counted in
 * `output_tokens` but dropped from replay (`checkpoint_hygiene.py` —
 * "reasoning from closed turns is dropped"). That over-subtracted by however
 * much the model had reasoned, understating the turn and, on a short answer
 * with a long reasoning block, driving the figure negative. Live case: a turn
 * whose two tool rows read +2254 and +332 displayed 2534 new input tokens —
 * the parts visibly exceeded the whole.
 *
 * The previous answer therefore counts as output when produced and as input
 * when re-sent. That is not double counting: both are real, at different
 * rates.
 *
 * `previousContextTokens` is `0` before the first turn (nothing in context
 * yet, so a first turn's whole prompt is genuinely new) and `null` once the
 * chain is broken by a turn that reported no `contextTokens` — there, the
 * honest answer is "unknown", and the caller falls back to the billed total
 * rather than subtracting a stale anchor and understating the turn.
 */
export function marginalTokenUsage(
  contextTokens: number | null | undefined,
  billed: TokenUsage | null,
  previousContextTokens: number | null,
): TokenUsage | null {
  if (contextTokens == null || billed == null || previousContextTokens == null) return null;
  // Clamped: history trimming can leave a turn ending on a smaller context
  // than the one before it, and a negative "new tokens" reads as a bug.
  const newInput = Math.max(0, contextTokens - previousContextTokens);
  return {
    input_tokens: newInput,
    output_tokens: billed.output_tokens,
    total_tokens: newInput + billed.output_tokens,
    // Deliberately no cache_read_tokens: caching is a property of a whole
    // prompt, not of a delta. The header still reports it.
  };
}

/**
 * Conversation-level total for the chat header (#2403).
 *
 * Sums exactly what the per-message badges show, so the header reconciles with
 * the thread: a reader adding up the messages lands on the header figure.
 * Summing the provider's per-call usage there instead put 72 595 above two
 * messages reading 16 871 and 3 136 — the same parts-versus-whole mismatch
 * that made the per-tool badges unreadable, one level up.
 *
 * Because each turn's displayed input is `contextTokens(T) - contextTokens(T-1)`,
 * the sum telescopes to `contextTokens(last) + every output` — the tokens the
 * conversation actually holds.
 */
export function conversationTokenTotals(messages: ThreadMessage[]): TokenUsage {
  const total: TokenUsage = { input_tokens: 0, output_tokens: 0, total_tokens: 0 };

  for (const message of messages) {
    // Same fallback the badge applies: a turn with no marginal figure shows
    // its billed one, so the header must add the same number the reader sees.
    const shown = message.marginalTokenUsage ?? message.tokenUsage;
    if (!shown) continue;
    total.input_tokens += shown.input_tokens;
    total.output_tokens += shown.output_tokens;
    total.total_tokens += shown.total_tokens;
  }

  return total;
}

export function toThreadMessages(messages: ChatMessage[], isStreaming: boolean): ThreadMessage[] {
  const { order, groups } = groupByExchange(messages);

  const result: ThreadMessage[] = [];
  const lastEid = order[order.length - 1] as string | undefined;
  // Rolling anchor for the marginal computation above. Exchanges are walked
  // in order, so each turn sees the context the previous one ended on.
  //
  // Starting at 0 assumes `messages` is the WHOLE conversation, which the
  // history store currently guarantees (it has no pagination). If windowed
  // loading is ever added, the first loaded exchange would be a mid-
  // conversation turn measured against an empty context and would report its
  // entire prompt as new — seed this from the turn before the window instead
  // of 0, or pass null to fall back to the billed total.
  let previousContextTokens: number | null = 0;

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
      const part = hitlRespMsg.parts?.[0] as HitlResponsePart | undefined;
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
      let contextTokens: number | null = null;
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
        if (contextTokens === null && typeof meta?.context_tokens === "number") {
          contextTokens = meta.context_tokens;
        }
        if (sources.length === 0) {
          const srcs = meta?.sources as VectorSearchHit[] | undefined;
          if (srcs && srcs.length > 0) sources.push(...srcs);
        }
        if (tokenUsage && contextTokens !== null && sources.length > 0) break;
      }
      const marginal = marginalTokenUsage(contextTokens, tokenUsage, previousContextTokens);
      previousContextTokens = contextTokens;
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
        contextTokens,
        marginalTokenUsage: marginal,
      });
    }
  }

  return result;
}
