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

export const TRACE_CHANNELS: Channel[] = [
  "plan",
  "thought",
  "observation",
  "tool_call",
  "tool_result",
  "system_note",
  "error",
];
export const FINAL_CHANNELS: Channel[] = ["final"];

// Discriminated union representing one visual row in ThoughtTrace.
// A `solo` entry may carry an attached tool_call (+ result): this is a merged
// `tool_use` thought ("Calling X") that owns its tool call, so the trace shows one
// friendly row while the raw call/result stay available in the detail drawer.
export type TraceEntry =
  | { kind: "solo"; message: ChatMessage; toolCall?: ChatMessage; toolResult?: ChatMessage }
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

// Turn a raw tool name into a short, human-readable label. Mirrors the backend
// `_humanize_tool_name` (fred-runtime react_runtime.py) so orphan tool_call rows —
// those with no preceding `tool_use` thought — are never shown raw either.
export function humanizeToolName(name: string): string {
  const raw = name.trim();
  if (!raw) return "tool";
  let base = raw;
  if (raw.toLowerCase().startsWith("mcp__")) {
    const segments = raw.split("__").filter(Boolean);
    if (segments.length >= 2) base = segments[segments.length - 1];
  }
  const spaced = base.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
  return (
    spaced
      .split(/[\s_-]+/)
      .filter(Boolean)
      .join(" ") || "tool"
  );
}

// The tool_call / tool_result message backing an entry, if any — present on a
// `combo` or on a merged `tool_use` thought. Used by the detail drawer.
export function entryToolCall(entry: TraceEntry): ChatMessage | undefined {
  return entry.kind === "combo" ? entry.call : entry.toolCall;
}

export function entryToolResult(entry: TraceEntry): ChatMessage | undefined {
  return entry.kind === "combo" ? entry.result : entry.toolResult;
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

export type ThoughtExtras = {
  thought_id?: string;
  phase?: string;
  title?: string | null;
  conclusion?: string | null;
  duration_ms?: number | null;
  streaming_delta?: boolean;
  source?: string | null;
};

export function thoughtExtras(msg: ChatMessage): ThoughtExtras {
  return (msg.metadata?.extras as ThoughtExtras | undefined) ?? {};
}

export const PHASE_LABELS: Record<string, string> = {
  planning: "Planning",
  tool_use: "Tool use",
  observation: "Observation",
  reflection: "Reflection",
  synthesis: "Synthesis",
};

// Raw phase key (e.g. "planning") of a thought entry — used to colour the badge.
// Returns null for non-thought entries.
export function phaseKeyForEntry(entry: TraceEntry): string | null {
  if (entry.kind !== "solo" || entry.message.channel !== "thought") return null;
  return thoughtExtras(entry.message).phase ?? null;
}

// "model_native" | "authored" | null — where the reasoning came from.
export function sourceForEntry(entry: TraceEntry): string | null {
  if (entry.kind !== "solo") return null;
  return thoughtExtras(entry.message).source ?? null;
}

// Full accumulated reasoning / note text of a solo entry (for markdown rendering).
export function detailTextForEntry(entry: TraceEntry): string {
  if (entry.kind !== "solo") return "";
  return textOf(entry.message);
}

// Stable identity for a trace entry. The detail drawer stores this key (not the
// entry object) so it can re-resolve the entry against the live message list and
// stream reasoning deltas in real time instead of showing a frozen snapshot.
export function traceEntryKey(entry: TraceEntry): string {
  if (entry.kind === "combo") return `tool:${toolCallId(entry.call)}`;
  const msg = entry.message;
  const id = thoughtExtras(msg).thought_id;
  return id ? `thought:${id}` : `msg:${msg.exchange_id}:${msg.rank}`;
}

// Re-resolve a previously-selected entry from the current messages (null if gone).
export function findTraceEntry(messages: ChatMessage[], key: string): TraceEntry | null {
  for (const entry of groupTraceEntries(messages)) {
    if (traceEntryKey(entry) === key) return entry;
  }
  return null;
}

// Primary label shown in the row (channel-based)
export function entryLabel(entry: TraceEntry): string {
  const channel = entry.kind === "combo" ? entry.call.channel : entry.message.channel;
  switch (channel) {
    case "thought": {
      const msg = entry.kind === "solo" ? entry.message : null;
      const extras = msg ? thoughtExtras(msg) : {};
      const phase = extras.phase ? (PHASE_LABELS[extras.phase] ?? extras.phase) : null;
      return phase ?? "Thought";
    }
    case "plan":
      return "Plan";
    case "observation":
      return "Observation";
    case "tool_call":
      return entry.kind === "combo" ? humanizeToolName(toolName(entry.call)) : "Tool call";
    case "tool_result":
      return "Tool result";
    case "system_note":
      return "System";
    case "error":
      return "Error";
    default:
      return channel;
  }
}

// Short preview text shown inline in the row
export function primaryTextForEntry(entry: TraceEntry): string {
  if (entry.kind === "solo") {
    if (entry.message.channel === "thought") {
      const extras = thoughtExtras(entry.message);
      return extras.title || textOf(entry.message);
    }
    return textOf(entry.message);
  }
  // combo: show humanized tool name + compact args preview
  const name = humanizeToolName(toolName(entry.call));
  const args = toolArgs(entry.call);
  const argStr = Object.keys(args).length
    ? Object.entries(args)
        .slice(0, 2)
        .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
        .join(", ")
    : "";
  return argStr ? `${name}(${argStr})` : name;
}

// Secondary text shown below primary (e.g., tool result summary, thought conclusion)
export function secondaryTextForEntry(entry: TraceEntry): string {
  if (entry.kind === "solo" && entry.message.channel === "thought") {
    const extras = thoughtExtras(entry.message);
    if (extras.conclusion) return extras.conclusion;
    if (extras.duration_ms != null) return formatLatencyMs(extras.duration_ms);
  }
  if (entry.kind === "combo" && entry.result) {
    return summarizeToolResultCompact(entry.result);
  }
  return "";
}

export function statusForEntry(entry: TraceEntry): TraceStatus {
  if (entry.kind === "solo") {
    // Merged tool_use thought: its status follows the underlying tool result.
    if (entry.toolCall) {
      if (!entry.toolResult) return "pending";
      return toolResultOk(entry.toolResult) ? "ok" : "error";
    }
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

  for (let i = 0; i < trace.length; i++) {
    const m = trace[i];
    if (isToolResult(m)) continue; // handled via combo / merged thought
    if (isToolCall(m)) {
      const callId = toolCallId(m);
      if (consumedCallIds.has(callId)) continue; // already merged into a tool_use thought
      consumedCallIds.add(callId);
      entries.push({ kind: "combo", call: m, result: resultMap.get(callId) });
      continue;
    }
    // Merge a `tool_use` thought with its immediately-following tool_call so the
    // friendly "Calling X" thought is the single visible row; the raw call + result
    // ride along for the detail drawer. They arrive adjacent because the runtime
    // emits ThoughtStart then ToolCall consecutively (RUNTIME-05 / CHAT-12).
    if (m.channel === "thought" && thoughtExtras(m).phase === "tool_use") {
      const next = trace[i + 1];
      if (next && isToolCall(next)) {
        const callId = toolCallId(next);
        consumedCallIds.add(callId);
        entries.push({
          kind: "solo",
          message: m,
          toolCall: next,
          toolResult: resultMap.get(callId),
        });
        continue;
      }
    }
    entries.push({ kind: "solo", message: m });
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
