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

import type { Channel, ChatMessage, ToolCallPart, ToolResultPart } from "../../slices/agentic/agenticOpenApi";

export const TRACE_CHANNELS: Channel[] = ["plan", "thought", "observation", "tool_call", "tool_result", "system_note", "error"];
export const FINAL_CHANNELS: Channel[] = ["final"];

// Discriminated union representing one visual row in ThoughtTrace
export type TraceEntry =
  | { kind: "solo"; message: ChatMessage }
  | { kind: "combo"; call: ChatMessage; result?: ChatMessage };

export type TraceStatus = "pending" | "ok" | "error" | "streaming";

export function isTraceChannel(channel: Channel): boolean {
  return TRACE_CHANNELS.includes(channel);
}

export function isFinalChannel(channel: Channel): boolean {
  return FINAL_CHANNELS.includes(channel);
}

function toolCallPart(msg: ChatMessage): ToolCallPart | undefined {
  const p = msg.parts?.[0];
  if (p?.type === "tool_call") return p as ToolCallPart;
  return undefined;
}

function toolResultPart(msg: ChatMessage): ToolResultPart | undefined {
  const p = msg.parts?.[0];
  if (p?.type === "tool_result") return p as ToolResultPart;
  return undefined;
}

export function isToolCall(msg: ChatMessage): boolean {
  return msg.channel === "tool_call" && toolCallPart(msg) !== undefined;
}

export function isToolResult(msg: ChatMessage): boolean {
  return msg.channel === "tool_result" && toolResultPart(msg) !== undefined;
}

export function toolCallId(msg: ChatMessage): string {
  return toolCallPart(msg)?.call_id ?? "";
}

export function toolResultId(msg: ChatMessage): string {
  return toolResultPart(msg)?.call_id ?? "";
}

export function toolName(msg: ChatMessage): string {
  return toolCallPart(msg)?.name ?? "";
}

export function toolArgs(msg: ChatMessage): Record<string, unknown> {
  return toolCallPart(msg)?.args ?? {};
}

export function toolResultOk(result: ChatMessage): boolean {
  return toolResultPart(result)?.ok !== false;
}

export function toolResultLatencyMs(result: ChatMessage): number | null {
  return toolResultPart(result)?.latency_ms ?? null;
}

export function toolResultContent(result: ChatMessage): string {
  return toolResultPart(result)?.content ?? "";
}

export function textOf(msg: ChatMessage): string {
  return (msg.parts ?? [])
    .filter((p) => p.type === "text")
    .map((p) => (p as { type: "text"; text: string }).text)
    .join("");
}

export function formatLatencyMs(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function summarizeToolResultCompact(result: ChatMessage, maxLen = 120): string {
  const content = toolResultContent(result);
  if (!content) return "";
  const single = content.replace(/\s+/g, " ").trim();
  return single.length > maxLen ? single.slice(0, maxLen) + "…" : single;
}

// Primary label shown in the row (channel-based)
export function entryLabel(entry: TraceEntry): string {
  const channel = entry.kind === "combo" ? entry.call.channel : entry.message.channel;
  switch (channel) {
    case "thought": return "Thought";
    case "plan": return "Plan";
    case "observation": return "Observation";
    case "tool_call": return entry.kind === "combo" ? toolName(entry.call) || "Tool" : "Tool call";
    case "tool_result": return "Tool result";
    case "system_note": return "System";
    case "error": return "Error";
    default: return channel;
  }
}

// Short preview text shown inline in the row
export function primaryTextForEntry(entry: TraceEntry): string {
  if (entry.kind === "solo") return textOf(entry.message);
  // combo: show tool name + compact args preview
  const name = toolName(entry.call);
  const args = toolArgs(entry.call);
  const argStr = Object.keys(args).length
    ? Object.entries(args)
        .slice(0, 2)
        .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
        .join(", ")
    : "";
  return argStr ? `${name}(${argStr})` : name;
}

// Secondary text shown below primary (e.g., tool result summary)
export function secondaryTextForEntry(entry: TraceEntry): string {
  if (entry.kind === "combo" && entry.result) {
    return summarizeToolResultCompact(entry.result);
  }
  return "";
}

export function statusForEntry(entry: TraceEntry): TraceStatus {
  if (entry.kind === "solo") {
    const extras = entry.message.metadata?.extras as { streaming_delta?: boolean } | undefined;
    if (extras?.streaming_delta) return "streaming";
    if (entry.message.channel === "error") return "error";
    return "ok";
  }
  // combo
  if (!entry.result) return "pending";
  return toolResultOk(entry.result) ? "ok" : "error";
}

// Groups trace-channel messages from one exchange into TraceEntry[]
// Pairs tool_call + tool_result by call_id; everything else is solo.
export function groupTraceEntries(messages: ChatMessage[]): TraceEntry[] {
  const trace = messages.filter((m) => isTraceChannel(m.channel));
  const resultMap = new Map<string, ChatMessage>();
  for (const m of trace) {
    if (isToolResult(m)) {
      const id = toolResultId(m);
      if (id) resultMap.set(id, m);
    }
  }

  const entries: TraceEntry[] = [];
  const consumedCallIds = new Set<string>();

  for (const m of trace) {
    if (isToolResult(m)) continue; // handled via combo
    if (isToolCall(m)) {
      const callId = toolCallId(m);
      consumedCallIds.add(callId);
      const result = resultMap.get(callId);
      entries.push({ kind: "combo", call: m, result });
    } else {
      entries.push({ kind: "solo", message: m });
    }
  }

  // Orphan tool_results (no matching call — shouldn't happen but be safe)
  for (const m of trace) {
    if (isToolResult(m) && !consumedCallIds.has(toolResultId(m))) {
      entries.push({ kind: "solo", message: m });
    }
  }

  return entries;
}

// Compute total wall-clock latency across all combo entries with results
export function totalLatencyMs(entries: TraceEntry[]): number {
  return entries.reduce((acc, e) => {
    if (e.kind === "combo" && e.result) {
      return acc + (toolResultLatencyMs(e.result) ?? 0);
    }
    return acc;
  }, 0);
}

// Format "Thought for Xs" summary line
export function thoughtSummaryLabel(entries: TraceEntry[]): string {
  const ms = totalLatencyMs(entries);
  if (ms > 0) return `Thought for ${formatLatencyMs(ms)}`;
  return "Thought…";
}
