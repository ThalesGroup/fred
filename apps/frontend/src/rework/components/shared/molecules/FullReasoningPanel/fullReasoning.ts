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

import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import {
  entryLabel,
  groupTraceEntries,
  isReasoningEntry,
  statusForEntry,
  textOf,
  thoughtExtras,
  traceEntryKey,
} from "../../../../utils/traceUtils";

export type ReasoningStep =
  | { kind: "reasoning"; key: string; text: string; durationMs: number | null; streaming: boolean }
  | { kind: "tools"; key: string; labels: string[] };

export type ReasoningTurn = { exchangeId: string; question: string; steps: ReasoningStep[] };

/**
 * The conversation's reasoning, turn by turn, in full: every reasoning block
 * untrimmed, with the tool calls that ran BETWEEN two blocks collapsed into one
 * marker — they are why the reasoning resumed. Turns without reasoning are left out.
 */
export function fullReasoning(messages: ChatMessage[]): ReasoningTurn[] {
  const exchanges = new Map<string, ChatMessage[]>();
  for (const message of messages) {
    const group = exchanges.get(message.exchange_id);
    if (group) group.push(message);
    else exchanges.set(message.exchange_id, [message]);
  }

  const turns: ReasoningTurn[] = [];
  for (const [exchangeId, group] of exchanges) {
    const userMessage = group.find((m) => m.role === "user" && (m.channel as string) !== "hitl_response");
    const question = userMessage ? textOf(userMessage) : "";
    const steps: ReasoningStep[] = [];
    let pendingTools: { key: string; labels: string[] } | null = null;

    for (const entry of groupTraceEntries(group)) {
      if (entry.kind === "combo") {
        pendingTools ??= { key: traceEntryKey(entry), labels: [] };
        pendingTools.labels.push(entryLabel(entry));
        continue;
      }
      if (!isReasoningEntry(entry)) continue;
      const streaming = statusForEntry(entry) === "streaming";
      const text = textOf(entry.message);
      if (!text && !streaming) continue;
      if (pendingTools && steps.length > 0) steps.push({ kind: "tools", ...pendingTools });
      pendingTools = null;
      const durationMs = thoughtExtras(entry.message).duration_ms ?? null;
      steps.push({ kind: "reasoning", key: traceEntryKey(entry), text, durationMs, streaming });
    }

    if (steps.length > 0) turns.push({ exchangeId, question: question.trim(), steps });
  }
  return turns;
}

/** The same reasoning as one markdown document, for the clipboard. */
export function fullReasoningMarkdown(turns: ReasoningTurn[]): string {
  return turns
    .map((turn) => {
      const steps = turn.steps.map((step) =>
        step.kind === "reasoning" ? step.text.trim() : `_→ ${step.labels.join(", ")}_`,
      );
      const heading = turn.question ? [`## ${turn.question.replace(/\s+/g, " ")}`] : [];
      return [...heading, ...steps].join("\n\n");
    })
    .join("\n\n");
}
