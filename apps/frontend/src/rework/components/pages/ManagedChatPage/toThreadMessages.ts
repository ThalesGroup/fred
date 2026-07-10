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
import type { RawUiPart } from "@rework/types/parts";
import type { ThreadMessage } from "@rework/types/thread";
import type { TokenUsage } from "@rework/types/conversation";
import { isTraceChannel, textOf, uiPartsOf } from "../../../utils/traceUtils";

export function toThreadMessages(messages: ChatMessage[], isStreaming: boolean): ThreadMessage[] {
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
    if (hitlReqMsg) {
      type ReqPart = { question?: string; choices?: Array<{ id: string; label: string }>; title?: string | null };
      const part = hitlReqMsg.parts?.[0] as unknown as ReqPart | undefined;
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

    const hitlRespMsg = msgs.find((m) => (m.channel as string) === "hitl_response");
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
