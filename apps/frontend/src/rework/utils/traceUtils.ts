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

import type {
  Channel,
  ChatMessage,
  ToolCallPart,
  ToolResultPart,
  VectorSearchHit,
} from "../../slices/runtime/runtimeOpenApi";
import type { RawUiPart } from "@rework/types/parts";

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

// Discriminated union representing one visual row in ThoughtTrace
export type TraceEntry =
  | { kind: "solo"; message: ChatMessage }
  | { kind: "combo"; call: ChatMessage; result?: ChatMessage };

export type TraceStatus = "pending" | "awaiting_confirmation" | "ok" | "error" | "streaming";

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

// Maps known provider identifiers (from mcp__<provider>__ prefix) to display names.
// Providers not listed here fall back to title-cased provider string.
const PROVIDER_DISPLAY: Record<string, string> = {
  github: "GitHub",
  gitlab: "GitLab",
  jira: "Jira",
  confluence: "Confluence",
  slack: "Slack",
  notion: "Notion",
  google: "Google",
  linear: "Linear",
};

// Well-known compound slugs that don't follow the verb-first pattern.
// Also covers raw tool names emitted by specific MCP servers (no server prefix
// because langchain-mcp-adapters defaults to tool_name_prefix=False).
const SLUG_OVERRIDES: Record<string, string> = {
  web_search: "Searching the web",
  search_web: "Searching the web",
  browse_web: "Browsing the web",
  // tavily-mcp v0.2.x reports its tool as "tavily-search"
  "tavily-search": "Searching the web",
  tavily_search: "Searching the web",
  // ppt_filler capability: the raw tool name would render as "Fill Ppt Template"
  fill_ppt_template: "Generating the PowerPoint",
};

// Action verb stems → gerund display form.
const GERUNDS: Record<string, string> = {
  search: "Searching",
  find: "Finding",
  get: "Getting",
  fetch: "Fetching",
  read: "Reading",
  list: "Listing",
  create: "Creating",
  update: "Updating",
  delete: "Deleting",
  add: "Adding",
  remove: "Removing",
  send: "Sending",
  post: "Posting",
  run: "Running",
  execute: "Executing",
  query: "Querying",
  browse: "Browsing",
  write: "Writing",
};

function toTitleCase(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s;
}

/**
 * Bare tool slug of a raw tool name: MCP prefix and provider dropped, trailing
 * numeric suffix stripped. `mcp__knowledge_flow__read_query_2` → `read_query`.
 */
export function toolSlug(rawName: string): string {
  let slug = rawName;
  if (slug.startsWith("mcp__")) {
    const parts = slug.split("__");
    slug = parts.length >= 3 ? parts.slice(2).join("_") : parts.slice(1).join("_");
  }
  return slug.replace(/_\d+$/, "");
}

/**
 * Converts a raw tool name into a human-friendly label.
 *
 * Examples:
 *   mcp__tavily__web_search   → "Searching the web"
 *   mcp__github__search_issues → "Searching GitHub issues"
 *   mcp__jira__create_ticket   → "Creating Jira ticket"
 *   my_custom_tool_3           → "My Custom Tool"
 */
export function humanizeToolName(rawName: string): string {
  if (!rawName) return "Tool";

  let provider = "";

  if (rawName.startsWith("mcp__")) {
    const parts = rawName.split("__");
    if (parts.length >= 3) provider = parts[1].toLowerCase();
  }

  const slug = toolSlug(rawName);

  // Explicit overrides for well-known compound slugs
  if (SLUG_OVERRIDES[slug]) return SLUG_OVERRIDES[slug];

  const providerLabel = PROVIDER_DISPLAY[provider] ?? "";
  const words = slug.split("_").filter(Boolean);

  if (words.length === 0) return providerLabel || toTitleCase(rawName) || "Tool";

  // Verb at start: search_issues → "Searching [Provider] issues"
  const firstWord = words[0].toLowerCase();
  const startGerund = GERUNDS[firstWord];
  if (startGerund) {
    const obj = words.slice(1).join(" ").toLowerCase();
    if (providerLabel && obj) return `${startGerund} ${providerLabel} ${obj}`;
    if (providerLabel) return `${startGerund} ${providerLabel}`;
    if (obj) return `${startGerund} ${obj}`;
    return startGerund;
  }

  // Verb at end: code_search → "Searching code" (fallback after SLUG_OVERRIDES)
  const lastWord = words[words.length - 1].toLowerCase();
  const endGerund = GERUNDS[lastWord];
  if (endGerund && words.length > 1) {
    const obj = words.slice(0, -1).join(" ").toLowerCase();
    if (providerLabel && obj) return `${endGerund} ${providerLabel} ${obj}`;
    if (providerLabel) return `${endGerund} ${providerLabel}`;
    if (obj) return `${endGerund} ${obj}`;
    return endGerund;
  }

  // Fallback: title-case each word, append provider in parens if known
  const humanWords = words.map(toTitleCase).join(" ");
  return providerLabel ? `${humanWords} (${providerLabel})` : humanWords;
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

// The closed set of message-body part kinds (`ChatMessage.parts` proper).
// Everything OUTSIDE this set is a chat part riding in from `ui_parts`
// (link, geo, capability parts, kinds this build has never heard of) and
// must be RETAINED raw (#1977) — the part-renderer registry decides at
// render time what it can draw and silently skips the rest.
const MESSAGE_PART_TYPES: ReadonlySet<string> = new Set([
  "text",
  "code",
  "image_url",
  "tool_call",
  "tool_result",
  "hitl_request",
  "hitl_response",
]);

/** Key-order-independent identity, so the same part from two carriers matches. */
function canonicalPart(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalPart).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : 1));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalPart(v)}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

const isUiPart = (p: { type?: unknown } | undefined): boolean =>
  typeof p?.type === "string" && !MESSAGE_PART_TYPES.has(p.type);

/**
 * All chat parts (ui_parts) carried on a message, unknown kinds included.
 *
 * Two carriers: a streamed message holds them inline in `parts`, a stored one on
 * `metadata.ui_parts`. Full rationale: RUNTIME-EXECUTION-CONTRACT.md §8.59.
 */
export function uiPartsOf(msg: ChatMessage): RawUiPart[] {
  const inline = (msg.parts ?? []).filter(isUiPart) as unknown as RawUiPart[];
  const stored = ((msg.metadata?.ui_parts ?? []) as unknown as RawUiPart[]).filter(isUiPart);
  // The common cases by far, and the only ones a session ever hits today: a turn
  // is either streaming or replayed, never both. Skips the canonical keying.
  if (stored.length === 0) return inline;
  if (inline.length === 0) return stored;

  const seen = new Set(inline.map(canonicalPart));
  return [...inline, ...stored.filter((p) => !seen.has(canonicalPart(p)))];
}

export function formatLatencyMs(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// Recognized, curated tool-result content shapes. A tool result whose content
// doesn't match one of these stays redacted in the drawer (raw content from an
// unrecognized tool must not be shown to end users) — these two are common and
// specifically useful enough to justify a dedicated, richer view.
export type SqlQueryResult = {
  sql_query: string;
  rows: Record<string, unknown>[];
  error?: string | null;
};

export type RagSearchResult = {
  query: string;
  hits: VectorSearchHit[];
};

/** Parses a tool result's content string as a JSON object, or null if it isn't one. */
export function parseToolResultContent(result: ChatMessage): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(toolResultContent(result));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export function asSqlQueryResult(data: Record<string, unknown> | null): SqlQueryResult | null {
  if (data && typeof data.sql_query === "string" && Array.isArray(data.rows)) {
    return data as unknown as SqlQueryResult;
  }
  return null;
}

export function asRagSearchResult(data: Record<string, unknown> | null): RagSearchResult | null {
  if (data && typeof data.query === "string" && Array.isArray(data.hits)) {
    return data as unknown as RagSearchResult;
  }
  return null;
}

// summarize_document / list_document_tree (first-party document capabilities, not
// third-party MCP tools) return their content as plain prose/tree text, not a JSON
// envelope — there's no shape to sniff, so these two are recognized by tool name
// instead of by parsed-content shape. Still a curated allowlist, not a blanket
// "show raw text for any tool" rule.
export function isSummarizeDocumentTool(name: string): boolean {
  return name === "summarize_document";
}

export function isDocumentTreeTool(name: string): boolean {
  return name === "list_document_tree";
}

/** Strips list_document_tree's bracketed internal ids before display — document
 *  uids on leaves and `[folder:tag-id]` ids on folder lines (issue #2244) —
 *  same "never show this id to the user" rule the tool's docstring imposes on the
 *  model's own answers (identifier hygiene, shared with summarize_document). */
export function stripDocumentUids(tree: string): string {
  return tree.replace(/\s*\[[\w:-]+\]/g, "");
}

/** Curated {action, status, latency} payload for tool results with no recognized richer shape. */
export function genericToolPayload(entry: Extract<TraceEntry, { kind: "combo" }>): Record<string, unknown> {
  const action = humanizeToolName(toolName(entry.call));
  if (!entry.result) return { action, status: "running" };
  return {
    action,
    status: toolResultOk(entry.result) ? "completed" : "failed",
    latency: formatLatencyMs(toolResultLatencyMs(entry.result)),
  };
}

/** Text for the drawer header's single copy action, or null when there's nothing to copy. */
export function toolCopyText(entry: TraceEntry): string | null {
  // Error rows: the raw crash message is copyable from the drawer.
  if (entry.kind === "solo") {
    return entry.message.channel === "error" ? textOf(entry.message) || null : null;
  }
  const data = entry.result ? parseToolResultContent(entry.result) : null;
  const sqlResult = asSqlQueryResult(data);
  if (sqlResult) return sqlResult.sql_query;
  const ragResult = asRagSearchResult(data);
  if (ragResult) return null; // sources are browsed via SourcesPanel, not copied as text
  if (entry.result && isSummarizeDocumentTool(toolName(entry.call))) return toolResultContent(entry.result);
  if (entry.result && isDocumentTreeTool(toolName(entry.call)))
    return stripDocumentUids(toolResultContent(entry.result));
  return JSON.stringify(genericToolPayload(entry), null, 2);
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

/**
 * Flattens markdown to plain text for a one-glance preview.
 *
 * Reasoning text is markdown, and models emphasise heavily — a clamped preview
 * rendered raw shows literal `**Chiffre d'Affaires**` to the user. Previews are
 * clamped to two lines, so running them through the real markdown renderer
 * would be both heavy and pointless (block layout inside a clamped line box);
 * the full markdown is one click away in the detail drawer.
 *
 * Single `_` emphasis is deliberately NOT stripped: it would mangle the
 * snake_case identifiers that reasoning text is full of.
 */
export function plainPreviewText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s{0,3}>\s?/gm, "")
    .replace(/^\s{0,3}[-*+]\s+/gm, "")
    .replace(/(\*\*\*|___)(.+?)\1/g, "$2")
    .replace(/(\*\*|__)(.+?)\1/g, "$2")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/~~(.+?)~~/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
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
      return entry.kind === "combo" ? humanizeToolName(toolName(entry.call)) || "Tool" : "Tool call";
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
    // Error rows keep the line short (a localized indication rendered by the
    // row); the raw message is browsable in the trace drawer, not dumped inline.
    if (entry.message.channel === "error") return "";
    if (entry.message.channel === "thought") {
      const extras = thoughtExtras(entry.message);
      return extras.title || textOf(entry.message);
    }
    return textOf(entry.message);
  }
  // combo: the humanized label from entryLabel() is sufficient.
  // Raw tool name and arguments must not be shown to end users.
  return "";
}

// Secondary text shown below primary (e.g., thought conclusion, tool latency)
export function secondaryTextForEntry(entry: TraceEntry): string {
  if (entry.kind === "solo" && entry.message.channel === "thought") {
    const extras = thoughtExtras(entry.message);
    if (extras.conclusion) return extras.conclusion;
    if (extras.duration_ms != null) return formatLatencyMs(extras.duration_ms);
  }
  if (entry.kind === "combo" && entry.result) {
    // Show only the execution latency — never raw result content (which is often
    // a JSON payload from an external API and must not be exposed to end users).
    return formatLatencyMs(toolResultLatencyMs(entry.result));
  }
  return "";
}

/**
 * `pendingToolCallIds` are the `call_id`s of every tool call currently gated
 * behind ONE unanswered HITL confirmation prompt (#2177: a single prompt can
 * cover several calls at once — e.g. summarizing every document in a folder
 * — so this is a list, not one id). The backend streams a tool call's
 * `ToolCallRuntimeEvent` the moment the model proposes it — a separate,
 * earlier graph step than the HITL gate that pauses for approval — so a
 * gated call always arrives with no result yet, indistinguishable from one
 * already executing unless the caller tells us which call_ids are actually
 * still waiting on the human.
 */
export function statusForEntry(entry: TraceEntry, pendingToolCallIds?: readonly string[] | null): TraceStatus {
  if (entry.kind === "solo") {
    const extras = entry.message.metadata?.extras as { streaming_delta?: boolean } | undefined;
    if (extras?.streaming_delta) return "streaming";
    if (entry.message.channel === "error") return "error";
    return "ok";
  }
  // combo
  if (!entry.result) {
    if (pendingToolCallIds?.includes(toolCallId(entry.call))) return "awaiting_confirmation";
    return "pending";
  }
  return toolResultOk(entry.result) ? "ok" : "error";
}

/**
 * True when a combo tool entry was cancelled by the user at its HITL gate. The
 * frontend injects an optimistic error tool_result flagged `cancelled_by_user`
 * on cancel (see `useChatSse.sendHitlResume`), so the previously "running" row
 * flips immediately to a cancelled state (red status dot) instead of hanging.
 */
export function isCancelledByUser(entry: TraceEntry): boolean {
  if (entry.kind !== "combo" || !entry.result) return false;
  const extras = entry.result.metadata?.extras as { cancelled_by_user?: boolean } | undefined;
  return extras?.cancelled_by_user === true;
}

// A "tool_use" thought is a synthetic bookkeeping block the runtime opens/closes
// around every tool call purely to bracket it in time (see react_runtime.py).
// Its conclusion is always the hardcoded literal "Done"/"Error" and its title is
// just "Calling <tool>" — both fully redundant with the paired combo entry, which
// already shows the humanized tool label, the status dot, and (now) the real
// latency. Rendering it as a second row produced duplicate, information-free
// entries (the repeated "Done" rows). Filter it out entirely.
function isRedundantToolUseThought(m: ChatMessage): boolean {
  return m.channel === "thought" && thoughtExtras(m).phase === "tool_use";
}

// Groups trace-channel messages from one exchange into TraceEntry[]
// Pairs tool_call + tool_result by call_id; everything else is solo.
// Deduplicates tool_call messages sharing the same call_id (keeps first occurrence).
export function groupTraceEntries(messages: ChatMessage[]): TraceEntry[] {
  const trace = messages.filter((m) => isTraceChannel(m.channel) && !isRedundantToolUseThought(m));

  // Remove duplicate tool_call messages for the same call_id (e.g. from stream replay)
  const seenCallIds = new Set<string>();
  const unique = trace.filter((m) => {
    if (isToolCall(m)) {
      const id = toolCallId(m);
      if (!id || seenCallIds.has(id)) return false;
      seenCallIds.add(id);
    }
    return true;
  });

  const resultMap = new Map<string, ChatMessage>();
  for (const m of unique) {
    if (isToolResult(m)) {
      const id = toolResultId(m);
      if (id) resultMap.set(id, m);
    }
  }

  const entries: TraceEntry[] = [];
  const consumedCallIds = new Set<string>();

  for (const m of unique) {
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
  for (const m of unique) {
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

// ── Trace rows: one chronological sequence ───────────────────────────────────
//
// A turn is reasoning, then a tool, then more reasoning, then another tool. The
// trace shows it in that order: `groupTraceEntries` already returns entries by
// rank, which is stream arrival order, and a thought keeps the rank of its
// `thought_start` — so the sequence below is the real chronology, not a
// reconstruction.
//
// Reasoning and tool steps still render differently (a card vs a numbered row),
// because they remain two different species (#2172) — but they are no longer
// hoisted into two separate lanes, which put every thought above every tool and
// reported an order that never happened.

/** A tool call paired with its result (or still awaiting one). */
export type ToolEntry = Extract<TraceEntry, { kind: "combo" }>;

/** One row of the trace. `index` is the 1-based tool step number — null for
 *  reasoning, notes and errors, which are sequenced but are not steps. */
export type TraceRow = { entry: TraceEntry; lane: "reasoning" | "step"; index: number | null };

function isStepEntry(entry: TraceEntry): boolean {
  // Orphan tool_results (call never seen) land here too: they are tool activity.
  return entry.kind === "combo" || entry.message.channel === "tool_result";
}

function isReasoningEntry(entry: TraceEntry): boolean {
  if (entry.kind !== "solo") return false;
  const channel = entry.message.channel;
  return channel === "thought" || channel === "plan" || channel === "observation";
}

/** The trace as one chronological list, each row tagged with how it renders. */
export function traceRows(entries: TraceEntry[]): TraceRow[] {
  let toolIndex = 0;

  return entries.map((entry) => {
    if (isReasoningEntry(entry)) return { entry, lane: "reasoning" as const, index: null };
    if (isStepEntry(entry)) return { entry, lane: "step" as const, index: ++toolIndex };
    // system_note / error — sequenced with the steps, but unnumbered.
    return { entry, lane: "step" as const, index: null };
  });
}

// Tool slugs whose result volume IS a row count. A completed call to one of
// these always reports its count — zero included — because "0 rows" is the
// answer the reader needs (the query ran and found nothing, or came back in a
// shape we can't read), not an absence of information. Without this, a barren
// query rendered as a bare "Reading query" row, indistinguishable from a step
// still missing its metadata.
const ROW_COUNT_TOOL_SLUGS: ReadonlySet<string> = new Set(["read_query"]);

/**
 * Curated discriminator for a tool step, so two calls to the same tool are
 * distinguishable ("Reading query" ×2 was byte-identical before).
 *
 * Only volume metadata is derived — never raw arguments or raw result content,
 * which stay redacted per the rule enforced in {@link primaryTextForEntry}.
 * Returns null when the result shape is unrecognized, still running, or failed
 * (the red status dot already carries the failure).
 */
export function toolDiscriminator(entry: TraceEntry): { kind: "rows" | "sources"; count: number } | null {
  if (entry.kind !== "combo" || !entry.result || !toolResultOk(entry.result)) return null;
  const data = parseToolResultContent(entry.result);
  const sql = asSqlQueryResult(data);
  if (sql) return { kind: "rows", count: sql.error ? 0 : sql.rows.length };
  const rag = asRagSearchResult(data);
  if (rag) return { kind: "sources", count: rag.hits.length };
  if (ROW_COUNT_TOOL_SLUGS.has(toolSlug(toolName(entry.call)))) return { kind: "rows", count: 0 };
  return null;
}

export type TraceSummary = {
  /** Reasoning wall-clock, or null when no reasoning block reported one. */
  reasoningMs: number | null;
  /** Number of tool executions in this turn. */
  toolCount: number;
  /** Sum of tool execution latencies. */
  toolMs: number;
  /** Something is still streaming, awaiting a result, or awaiting confirmation. */
  running: boolean;
  /** At least one tool call is paused behind an unanswered HITL prompt. */
  awaitingConfirmation: boolean;
};

/**
 * Structured summary for the trace header. Returns data, not a string, so the
 * component formats it through i18n.
 *
 * `reasoningMs` is the SUM of the reasoning blocks' durations. It used to be
 * their MAX, because one model-native block spanned the whole turn and bracketed
 * the tool calls, so summing double-counted the same wall-clock. The runtime now
 * closes that block at every tool round, making the blocks disjoint — a max
 * would report only the longest stretch and hide the rest of the thinking.
 *
 * `pendingToolCallIds` — see {@link statusForEntry}.
 */
export function traceSummary(entries: TraceEntry[], pendingToolCallIds?: readonly string[] | null): TraceSummary {
  const rows = traceRows(entries);

  let reasoningMs: number | null = null;
  for (const { entry, lane } of rows) {
    if (lane !== "reasoning" || entry.kind !== "solo") continue;
    const duration = thoughtExtras(entry.message).duration_ms;
    if (duration != null) reasoningMs = (reasoningMs ?? 0) + duration;
  }

  const toolCount = rows.filter((r) => r.lane === "step" && r.entry.kind === "combo").length;
  const statuses = entries.map((e) => statusForEntry(e, pendingToolCallIds));
  const running = statuses.some((s) => s === "streaming" || s === "pending" || s === "awaiting_confirmation");
  const awaitingConfirmation = statuses.some((s) => s === "awaiting_confirmation");

  return { reasoningMs, toolCount, toolMs: totalLatencyMs(entries), running, awaitingConfirmation };
}
