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

import type { ChatMessage } from "../../slices/runtime/runtimeOpenApi";
import type { TraceRow, ToolEntry } from "./traceUtils";
import { isToolCall, toolCallId, traceEntryKey } from "./traceUtils";

export type TraceGroupRule = {
  id: string;
  titleKey: string;
  countKey: string;
  matches: (entry: ToolEntry) => boolean;
  itemLabel: (entry: ToolEntry) => string;
  preview: (entry: ToolEntry) => string;
};

export type TraceDisplayItem =
  | { kind: "row"; row: TraceRow; index: number | null }
  | { kind: "group"; key: string; rule: TraceGroupRule; rows: TraceRow[]; count: number; index: number };

/** Fold visual activities while leaving the stored call/result sequence intact. */
export function groupTraceRows(
  rows: TraceRow[],
  rules: readonly TraceGroupRule[],
  messages?: readonly ChatMessage[],
): TraceDisplayItem[] {
  const items: TraceDisplayItem[] = [];
  let active: Extract<TraceDisplayItem, { kind: "group" }> | null = null;
  let activeRun: number | undefined;
  let between: TraceRow[] = [];
  let displayIndex = 0;
  const runByCallId = new Map<string, number>();
  if (messages) {
    let run = 0;
    let previousRuleId: string | null = null;
    const seen = new Set<string>();
    for (const message of messages) {
      if (!isToolCall(message)) continue;
      const callId = toolCallId(message);
      if (!callId || seen.has(callId)) continue;
      seen.add(callId);
      const rule = rules.find((candidate) => candidate.matches({ kind: "combo", call: message }));
      if (!rule || rule.id !== previousRuleId) run++;
      if (rule) runByCallId.set(callId, run);
      previousRuleId = rule?.id ?? null;
    }
  }

  const flush = () => {
    if (active) items.push(active);
    active = null;
    activeRun = undefined;
    for (const row of between) items.push({ kind: "row", row, index: row.index === null ? null : ++displayIndex });
    between = [];
  };

  for (const row of rows) {
    const entry = row.entry;
    const rule = entry.kind === "combo" ? rules.find((candidate) => candidate.matches(entry)) : null;
    if (rule && entry.kind === "combo") {
      const run = messages ? runByCallId.get(toolCallId(entry.call)) : undefined;
      if (active?.rule.id === rule.id && (!messages || (run !== undefined && run === activeRun))) {
        active.rows.push(...between, row);
        active.count++;
        between = [];
      } else {
        flush();
        active = {
          kind: "group",
          key: `${rule.id}:${traceEntryKey(row.entry)}`,
          rule,
          rows: [row],
          count: 1,
          index: ++displayIndex,
        };
        activeRun = run;
      }
    } else if (active && row.lane === "reasoning") {
      between.push(row);
    } else {
      flush();
      items.push({ kind: "row", row, index: row.index === null ? null : ++displayIndex });
    }
  }
  flush();
  return items;
}
