import { describe, it, expect } from "vitest";
import type { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import {
  asRagSearchResult,
  asSqlQueryResult,
  formatLatencyMs,
  groupTraceEntries,
  humanizeToolName,
  isDocumentTreeTool,
  isTraceChannel,
  isFinalChannel,
  isSummarizeDocumentTool,
  parseToolResultContent,
  primaryTextForEntry,
  secondaryTextForEntry,
  splitTraceEntries,
  statusForEntry,
  stripDocumentUids,
  textOf,
  toolCopyText,
  toolDiscriminator,
  totalLatencyMs,
  traceSummary,
} from "./traceUtils";

// ── Factory ───────────────────────────────────────────────────────────────────

function msg(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    session_id: "s1",
    exchange_id: "e1",
    rank: 0,
    timestamp: "2026-01-01T00:00:00.000Z",
    role: "assistant",
    channel: "final",
    parts: [],
    ...overrides,
  };
}

function textMsg(text: string, overrides: Partial<ChatMessage> = {}): ChatMessage {
  return msg({ parts: [{ type: "text", text }], ...overrides });
}

function toolCallMsg(callId: string, name: string, args: Record<string, unknown> = {}): ChatMessage {
  return msg({
    channel: "tool_call",
    parts: [{ type: "tool_call", call_id: callId, name, args }],
  });
}

function toolResultMsg(callId: string, content: string, ok = true, latencyMs?: number): ChatMessage {
  return msg({
    channel: "tool_result",
    role: "tool",
    parts: [{ type: "tool_result", call_id: callId, ok, content, latency_ms: latencyMs ?? null }],
  });
}

function thoughtMsg(
  text: string,
  extras: {
    streaming_delta?: boolean;
    title?: string;
    conclusion?: string;
    phase?: string;
    duration_ms?: number;
    source?: string;
  } = {},
): ChatMessage {
  return msg({
    channel: "thought",
    parts: [{ type: "text", text }],
    metadata: { extras },
  });
}

// ── isTraceChannel / isFinalChannel ──────────────────────────────────────────

describe("isTraceChannel", () => {
  it("returns true for thought, tool_call, tool_result, plan, observation, error, system_note", () => {
    for (const ch of ["thought", "tool_call", "tool_result", "plan", "observation", "error", "system_note"] as const) {
      expect(isTraceChannel(ch), ch).toBe(true);
    }
  });

  it("returns false for final", () => {
    expect(isTraceChannel("final")).toBe(false);
  });
});

describe("isFinalChannel", () => {
  it("returns true for final only", () => {
    expect(isFinalChannel("final")).toBe(true);
    expect(isFinalChannel("thought")).toBe(false);
    expect(isFinalChannel("tool_call")).toBe(false);
  });
});

// ── textOf ───────────────────────────────────────────────────────────────────

describe("textOf", () => {
  it("returns text from text parts", () => {
    expect(textOf(textMsg("hello"))).toBe("hello");
  });

  it("concatenates multiple text parts", () => {
    const m = msg({
      parts: [
        { type: "text", text: "foo" },
        { type: "text", text: "bar" },
      ],
    });
    expect(textOf(m)).toBe("foobar");
  });

  it("ignores non-text parts", () => {
    const m = msg({ parts: [{ type: "tool_call", call_id: "c1", name: "search", args: {} }] });
    expect(textOf(m)).toBe("");
  });

  it("returns empty string for empty parts", () => {
    expect(textOf(msg({ parts: [] }))).toBe("");
  });
});

// ── formatLatencyMs ───────────────────────────────────────────────────────────

describe("formatLatencyMs", () => {
  it("returns empty string for null", () => {
    expect(formatLatencyMs(null)).toBe("");
  });

  it("formats sub-second as Xms", () => {
    expect(formatLatencyMs(0)).toBe("0ms");
    expect(formatLatencyMs(500)).toBe("500ms");
    expect(formatLatencyMs(999)).toBe("999ms");
  });

  it("formats >= 1000ms as X.Xs", () => {
    expect(formatLatencyMs(1000)).toBe("1.0s");
    expect(formatLatencyMs(1500)).toBe("1.5s");
    expect(formatLatencyMs(2750)).toBe("2.8s");
  });
});

// ── groupTraceEntries ─────────────────────────────────────────────────────────

describe("groupTraceEntries", () => {
  it("returns empty array for empty input", () => {
    expect(groupTraceEntries([])).toEqual([]);
  });

  it("returns empty array when messages contain no trace channels", () => {
    expect(groupTraceEntries([textMsg("hi", { channel: "final" })])).toEqual([]);
  });

  it("makes a solo entry for a thought message", () => {
    const t = thoughtMsg("thinking…");
    const entries = groupTraceEntries([t]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({ kind: "solo", message: t });
  });

  it("pairs a tool_call with its matching tool_result by call_id", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([call, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result });
  });

  it("pairs tool_call+result even when result appears before call in array", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([result, call]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result });
  });

  it("handles multiple distinct pairs correctly", () => {
    const call1 = toolCallMsg("c1", "search");
    const result1 = toolResultMsg("c1", "r1");
    const call2 = toolCallMsg("c2", "fetch");
    const result2 = toolResultMsg("c2", "r2");
    const entries = groupTraceEntries([call1, result1, call2, result2]);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({ kind: "combo", call: call1, result: result1 });
    expect(entries[1]).toMatchObject({ kind: "combo", call: call2, result: result2 });
  });

  it("marks combo as pending when tool_call has no matching result", () => {
    const call = toolCallMsg("c1", "search");
    const entries = groupTraceEntries([call]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result: undefined });
  });

  it("makes orphan tool_result a solo entry", () => {
    const orphan = toolResultMsg("c99", "unexpected");
    const entries = groupTraceEntries([orphan]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({ kind: "solo", message: orphan });
  });

  it("preserves thought solo entries alongside combos", () => {
    const thought = thoughtMsg("planning");
    const call = toolCallMsg("c1", "lookup");
    const result = toolResultMsg("c1", "data");
    const entries = groupTraceEntries([thought, call, result]);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toEqual({ kind: "solo", message: thought });
    expect(entries[1]).toMatchObject({ kind: "combo" });
  });

  it("filters out synthetic tool_use thought entries — redundant with the paired combo row", () => {
    const toolUseThought = thoughtMsg("", { phase: "tool_use", title: "Calling search", conclusion: "Done" });
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([toolUseThought, call, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result });
  });

  it("keeps non-tool_use thought phases (planning, reflection, synthesis) alongside combos", () => {
    const planning = thoughtMsg("thinking it through", { phase: "planning" });
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([planning, call, result]);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toEqual({ kind: "solo", message: planning });
    expect(entries[1]).toMatchObject({ kind: "combo", call, result });
  });
});

// ── statusForEntry ────────────────────────────────────────────────────────────

describe("statusForEntry", () => {
  it("returns 'streaming' for a streaming thought", () => {
    const m = thoughtMsg("partial…", { streaming_delta: true });
    expect(statusForEntry({ kind: "solo", message: m })).toBe("streaming");
  });

  it("returns 'error' for an error-channel message", () => {
    const m = msg({ channel: "error" });
    expect(statusForEntry({ kind: "solo", message: m })).toBe("error");
  });

  it("returns 'ok' for a completed solo thought", () => {
    const m = thoughtMsg("done");
    expect(statusForEntry({ kind: "solo", message: m })).toBe("ok");
  });

  it("returns 'pending' for a combo with no result yet", () => {
    const call = toolCallMsg("c1", "search");
    expect(statusForEntry({ kind: "combo", call })).toBe("pending");
  });

  it("returns 'ok' for a combo with a successful result", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found", true);
    expect(statusForEntry({ kind: "combo", call, result })).toBe("ok");
  });

  it("returns 'error' for a combo with a failed result", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "boom", false);
    expect(statusForEntry({ kind: "combo", call, result })).toBe("error");
  });

  it("returns 'awaiting_confirmation' for a combo whose call_id is in the pending HITL id list", () => {
    const call = toolCallMsg("c1", "summarize_document");
    expect(statusForEntry({ kind: "combo", call }, ["c1"])).toBe("awaiting_confirmation");
  });

  it("returns 'awaiting_confirmation' for EACH call batched into one HITL prompt (#2177)", () => {
    expect(statusForEntry({ kind: "combo", call: toolCallMsg("c1", "summarize_document") }, ["c1", "c2", "c3"])).toBe(
      "awaiting_confirmation",
    );
    expect(statusForEntry({ kind: "combo", call: toolCallMsg("c2", "summarize_document") }, ["c1", "c2", "c3"])).toBe(
      "awaiting_confirmation",
    );
  });

  it("returns 'pending' for a combo with no result yet when a DIFFERENT call is pending confirmation", () => {
    const call = toolCallMsg("c1", "search");
    expect(statusForEntry({ kind: "combo", call }, ["c-other"])).toBe("pending");
  });
});

// ── primaryTextForEntry ───────────────────────────────────────────────────────

describe("primaryTextForEntry", () => {
  it("returns thought title when set", () => {
    const m = thoughtMsg("long body", { title: "My Title" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("My Title");
  });

  it("falls back to thought body when no title", () => {
    const m = thoughtMsg("body text");
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("body text");
  });

  it("returns body text for non-thought solo entries", () => {
    const m = textMsg("some output", { channel: "plan" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("some output");
  });

  it("returns empty string for combo with args — raw tool name and arguments are suppressed", () => {
    const call = toolCallMsg("c1", "search", { query: "vitest" });
    expect(primaryTextForEntry({ kind: "combo", call })).toBe("");
  });

  it("returns empty string for combo with no args", () => {
    const call = toolCallMsg("c1", "refresh", {});
    expect(primaryTextForEntry({ kind: "combo", call })).toBe("");
  });

  it("shows tool_use thought title (e.g. 'Calling tavily search')", () => {
    const m = thoughtMsg("", { title: "Calling tavily search", phase: "tool_use" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("Calling tavily search");
  });

  it("shows title for non-tool_use thought phases", () => {
    const m = thoughtMsg("body", { title: "Planning step", phase: "planning" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("Planning step");
  });
});

// ── secondaryTextForEntry ────────────────────────────────────────────────────

describe("secondaryTextForEntry", () => {
  it("returns conclusion for a completed thought", () => {
    const m = thoughtMsg("body", { conclusion: "All good" });
    expect(secondaryTextForEntry({ kind: "solo", message: m })).toBe("All good");
  });

  it("returns latency string for combo with result that has latency", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "The answer is 42", true, 1500);
    expect(secondaryTextForEntry({ kind: "combo", call, result })).toBe("1.5s");
  });

  it("returns empty string when result has no latency", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", '{"raw":"json response"}');
    expect(secondaryTextForEntry({ kind: "combo", call, result })).toBe("");
  });

  it("does not expose raw result content", () => {
    const call = toolCallMsg("c1", "get_issue");
    const result = toolResultMsg("c1", '{"expand":"renderedFields,names,schema","summary":"Secret data"}');
    const text = secondaryTextForEntry({ kind: "combo", call, result });
    expect(text).not.toContain("renderedFields");
    expect(text).not.toContain("Secret");
    expect(text).not.toContain("{");
  });

  it("returns empty string for pending combo", () => {
    const call = toolCallMsg("c1", "search");
    expect(secondaryTextForEntry({ kind: "combo", call })).toBe("");
  });
});

// ── totalLatencyMs ────────────────────────────────────────────────────────────

describe("totalLatencyMs", () => {
  it("returns 0 for empty entries", () => {
    expect(totalLatencyMs([])).toBe(0);
  });

  it("sums latencies of all combo results", () => {
    const entries = [
      { kind: "combo" as const, call: toolCallMsg("c1", "a"), result: toolResultMsg("c1", "r1", true, 100) },
      { kind: "combo" as const, call: toolCallMsg("c2", "b"), result: toolResultMsg("c2", "r2", true, 250) },
    ];
    expect(totalLatencyMs(entries)).toBe(350);
  });

  it("ignores solo entries and pending combos", () => {
    const entries = [
      { kind: "solo" as const, message: thoughtMsg("thinking") },
      { kind: "combo" as const, call: toolCallMsg("c1", "search") },
    ];
    expect(totalLatencyMs(entries)).toBe(0);
  });
});

// ── splitTraceEntries ─────────────────────────────────────────────────────────

describe("splitTraceEntries", () => {
  it("returns empty lanes for an empty trace", () => {
    expect(splitTraceEntries([])).toEqual({ reasoning: [], steps: [] });
  });

  it("routes reasoning channels to the reasoning lane, never to the steps", () => {
    const planning = thoughtMsg("thinking", { phase: "planning" });
    const plan = msg({ channel: "plan", parts: [{ type: "text", text: "step 1" }] });
    const observation = msg({ channel: "observation", parts: [{ type: "text", text: "noted" }] });
    const lanes = splitTraceEntries([
      { kind: "solo", message: planning },
      { kind: "solo", message: plan },
      { kind: "solo", message: observation },
    ]);
    expect(lanes.reasoning).toHaveLength(3);
    expect(lanes.steps).toEqual([]);
  });

  it("numbers tool steps 1-based in arrival order", () => {
    const entries = [
      { kind: "combo" as const, call: toolCallMsg("c1", "read_query"), result: toolResultMsg("c1", "{}", true, 100) },
      { kind: "combo" as const, call: toolCallMsg("c2", "read_query"), result: toolResultMsg("c2", "{}", true, 200) },
    ];
    const lanes = splitTraceEntries(entries);
    expect(lanes.steps.map((s) => s.index)).toEqual([1, 2]);
  });

  it("keeps the reasoning block out of the step numbering", () => {
    const planning = thoughtMsg("thinking", { phase: "planning" });
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found", true, 50);
    const lanes = splitTraceEntries(groupTraceEntries([planning, call, result]));
    expect(lanes.reasoning).toHaveLength(1);
    expect(lanes.steps).toHaveLength(1);
    expect(lanes.steps[0].index).toBe(1);
  });

  it("sequences notes and errors with the steps but leaves them unnumbered", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found", true, 50);
    const failure = msg({ channel: "error", parts: [{ type: "text", text: "boom" }] });
    const lanes = splitTraceEntries(groupTraceEntries([call, result, failure]));
    expect(lanes.steps.map((s) => s.index)).toEqual([1, null]);
  });
});

// ── traceSummary ──────────────────────────────────────────────────────────────

describe("traceSummary", () => {
  it("reports nothing for an empty trace", () => {
    expect(traceSummary([])).toEqual({
      reasoningMs: null,
      toolCount: 0,
      toolMs: 0,
      running: false,
      awaitingConfirmation: false,
    });
  });

  it("takes the MAX reasoning duration, not the sum — nested blocks share wall-clock", () => {
    const outer = thoughtMsg("outer", { phase: "planning", duration_ms: 16400 });
    const inner = thoughtMsg("inner", { phase: "reflection", duration_ms: 1200 });
    expect(
      traceSummary([
        { kind: "solo", message: outer },
        { kind: "solo", message: inner },
      ]).reasoningMs,
    ).toBe(16400);
  });

  it("counts tools and sums their latency separately from the reasoning duration", () => {
    const reasoning = thoughtMsg("thinking", { phase: "planning", duration_ms: 16400 });
    const entries = [
      { kind: "solo" as const, message: reasoning },
      { kind: "combo" as const, call: toolCallMsg("c1", "a"), result: toolResultMsg("c1", "r", true, 148) },
      { kind: "combo" as const, call: toolCallMsg("c2", "b"), result: toolResultMsg("c2", "r", true, 140) },
    ];
    expect(traceSummary(entries)).toEqual({
      reasoningMs: 16400,
      toolCount: 2,
      toolMs: 288,
      running: false,
      awaitingConfirmation: false,
    });
  });

  it("is running while a thought still streams", () => {
    const streaming = thoughtMsg("partial…", { streaming_delta: true });
    expect(traceSummary([{ kind: "solo", message: streaming }]).running).toBe(true);
  });

  it("is running while a tool call awaits its result", () => {
    expect(traceSummary([{ kind: "combo", call: toolCallMsg("c1", "search") }]).running).toBe(true);
  });

  it("is running, and awaitingConfirmation, while a tool call is gated behind an unanswered HITL prompt", () => {
    const entries = [{ kind: "combo" as const, call: toolCallMsg("c1", "summarize_document") }];
    expect(traceSummary(entries, ["c1"])).toEqual({
      reasoningMs: null,
      toolCount: 1,
      toolMs: 0,
      running: true,
      awaitingConfirmation: true,
    });
  });

  it("is awaitingConfirmation for a batch of several calls gated by ONE combined HITL prompt (#2177)", () => {
    const entries = [
      { kind: "combo" as const, call: toolCallMsg("c1", "summarize_document") },
      { kind: "combo" as const, call: toolCallMsg("c2", "summarize_document") },
      { kind: "combo" as const, call: toolCallMsg("c3", "summarize_document") },
    ];
    const summary = traceSummary(entries, ["c1", "c2", "c3"]);
    expect(summary.awaitingConfirmation).toBe(true);
    expect(summary.running).toBe(true);
    expect(summary.toolCount).toBe(3);
  });

  it("does not mark awaitingConfirmation for an unrelated pending call_id", () => {
    const entries = [{ kind: "combo" as const, call: toolCallMsg("c1", "summarize_document") }];
    expect(traceSummary(entries, ["c-other"]).awaitingConfirmation).toBe(false);
  });
});

// ── toolDiscriminator ─────────────────────────────────────────────────────────

describe("toolDiscriminator", () => {
  it("reports the row count of a SQL result", () => {
    const result = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [{ a: 1 }, { a: 2 }] }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "read_query"), result })).toEqual({
      kind: "rows",
      count: 2,
    });
  });

  it("reports the hit count of a RAG result", () => {
    const result = toolResultMsg("c1", JSON.stringify({ query: "cars", hits: [{}, {}, {}] }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "search"), result })).toEqual({
      kind: "sources",
      count: 3,
    });
  });

  it("reports 0 rows for an empty SQL result instead of going bare", () => {
    const result = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [] }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "read_query"), result })).toEqual({
      kind: "rows",
      count: 0,
    });
  });

  it("reports 0 rows for a SQL result that carries an error", () => {
    const result = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [], error: "syntax error" }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "read_query"), result })).toEqual({
      kind: "rows",
      count: 0,
    });
  });

  it("reports 0 rows for a query whose result came back in an unreadable shape", () => {
    const opaque = toolResultMsg("c1", "Tool error: binder error on column CA");
    expect(
      toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "mcp__knowledge_flow__read_query"), result: opaque }),
    ).toEqual({
      kind: "rows",
      count: 0,
    });
  });

  it("returns null for unrecognized, pending, failed and solo entries", () => {
    const opaque = toolResultMsg("c1", "plain text");
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "x"), result: opaque })).toBeNull();
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "x") })).toBeNull();
    const failed = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [{ a: 1 }] }), false);
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "x"), result: failed })).toBeNull();
    expect(toolDiscriminator({ kind: "solo", message: thoughtMsg("thinking") })).toBeNull();
  });
});

// ── humanizeToolName ──────────────────────────────────────────────────────────

describe("humanizeToolName", () => {
  it("handles MCP web_search → 'Searching the web'", () => {
    expect(humanizeToolName("mcp__tavily__web_search")).toBe("Searching the web");
  });

  it("handles bare web_search (no mcp prefix)", () => {
    expect(humanizeToolName("web_search")).toBe("Searching the web");
  });

  it("handles MCP verb-first with provider: search_issues → 'Searching GitHub issues'", () => {
    expect(humanizeToolName("mcp__github__search_issues")).toBe("Searching GitHub issues");
  });

  it("handles MCP create with provider: create_ticket → 'Creating Jira ticket'", () => {
    expect(humanizeToolName("mcp__jira__create_ticket")).toBe("Creating Jira ticket");
  });

  it("strips trailing numeric suffix before humanizing", () => {
    expect(humanizeToolName("mcp__jira__create_ticket_3")).toBe("Creating Jira ticket");
    expect(humanizeToolName("search_2")).toBe("Searching");
  });

  it("falls back to title-cased words for unknown tools without verbs", () => {
    expect(humanizeToolName("my_custom_tool")).toBe("My Custom Tool");
  });

  it("strips numeric suffix on unknown tools", () => {
    expect(humanizeToolName("my_custom_tool_3")).toBe("My Custom Tool");
  });

  it("handles single-word verb tools", () => {
    expect(humanizeToolName("search")).toBe("Searching");
    expect(humanizeToolName("create")).toBe("Creating");
  });

  it("handles tavily-search (raw name from tavily-mcp v0.2.x)", () => {
    expect(humanizeToolName("tavily-search")).toBe("Searching the web");
  });

  it("returns 'Tool' for empty string", () => {
    expect(humanizeToolName("")).toBe("Tool");
  });

  it("handles verb-at-end pattern (code_search)", () => {
    const result = humanizeToolName("code_search");
    expect(result).toContain("Searching");
    expect(result.toLowerCase()).toContain("code");
  });

  it("includes provider label for non-web MCP tools with no verb object", () => {
    expect(humanizeToolName("mcp__github__search")).toBe("Searching GitHub");
  });

  it("handles the ppt_filler capability tool (fill_ppt_template)", () => {
    expect(humanizeToolName("fill_ppt_template")).toBe("Generating the PowerPoint");
  });

  it("handles the writable_document capability tool (write_document)", () => {
    expect(humanizeToolName("write_document")).toBe("Writing document");
  });
});

// ── parseToolResultContent / asSqlQueryResult / asRagSearchResult ───────────

describe("parseToolResultContent", () => {
  it("parses valid JSON object content", () => {
    const result = toolResultMsg("c1", '{"foo":"bar"}');
    expect(parseToolResultContent(result)).toEqual({ foo: "bar" });
  });

  it("returns null for non-JSON content", () => {
    const result = toolResultMsg("c1", "plain text answer");
    expect(parseToolResultContent(result)).toBeNull();
  });

  it("returns null for JSON arrays (not an object)", () => {
    const result = toolResultMsg("c1", "[1,2,3]");
    expect(parseToolResultContent(result)).toBeNull();
  });
});

describe("asSqlQueryResult", () => {
  it("recognizes a RawSQLResponse-shaped object", () => {
    const data = { sql_query: "SELECT * FROM ships", rows: [{ id: 1 }], error: null };
    expect(asSqlQueryResult(data)).toEqual(data);
  });

  it("returns null when sql_query is missing", () => {
    expect(asSqlQueryResult({ rows: [] })).toBeNull();
  });

  it("returns null when rows is not an array", () => {
    expect(asSqlQueryResult({ sql_query: "SELECT 1", rows: "not an array" })).toBeNull();
  });

  it("returns null for null input", () => {
    expect(asSqlQueryResult(null)).toBeNull();
  });
});

describe("asRagSearchResult", () => {
  it("recognizes a {query, hits} shaped object", () => {
    const data = { query: "how many ships", hits: [{ uid: "u1", title: "t", content: "c", score: 0.9 }] };
    expect(asRagSearchResult(data)).toEqual(data);
  });

  it("returns null when query is missing", () => {
    expect(asRagSearchResult({ hits: [] })).toBeNull();
  });

  it("returns null when hits is not an array", () => {
    expect(asRagSearchResult({ query: "q", hits: "not an array" })).toBeNull();
  });

  it("returns null for null input", () => {
    expect(asRagSearchResult(null)).toBeNull();
  });

  it("does not misclassify a SQL result as a RAG result", () => {
    const sqlData = { sql_query: "SELECT 1", rows: [] };
    expect(asRagSearchResult(sqlData)).toBeNull();
  });
});

describe("isSummarizeDocumentTool / isDocumentTreeTool", () => {
  it("recognizes the exact first-party tool names only", () => {
    expect(isSummarizeDocumentTool("summarize_document")).toBe(true);
    expect(isSummarizeDocumentTool("list_document_tree")).toBe(false);
    expect(isSummarizeDocumentTool("mcp__tavily__web_search")).toBe(false);

    expect(isDocumentTreeTool("list_document_tree")).toBe(true);
    expect(isDocumentTreeTool("summarize_document")).toBe(false);
  });
});

describe("stripDocumentUids", () => {
  it("removes a bracketed uid after a document name", () => {
    expect(stripDocumentUids("report.pdf [doc-abc123] (2026-01-01)")).toBe("report.pdf (2026-01-01)");
  });

  it("strips uids on every line of a multi-line tree", () => {
    const tree = ["Sales", "  report.pdf [doc-1] (2026-01-01)", "  HR", "    notes.docx [doc-2] (2026-02-02)"].join(
      "\n",
    );
    expect(stripDocumentUids(tree)).toBe(
      ["Sales", "  report.pdf (2026-01-01)", "  HR", "    notes.docx (2026-02-02)"].join("\n"),
    );
  });

  it("leaves text with no bracketed uid unchanged", () => {
    expect(stripDocumentUids("Sales\n  HR")).toBe("Sales\n  HR");
  });

  it("strips folder tag ids rendered as [folder:tag-id] (issue #2244)", () => {
    const tree = ["docs [folder:8e0927eb-3650-4696-a21c-47e78d48f54f]/", "  report.pdf [doc-1] (2026-01-01)"].join(
      "\n",
    );
    expect(stripDocumentUids(tree)).toBe(["docs/", "  report.pdf (2026-01-01)"].join("\n"));
  });
});

describe("toolCopyText", () => {
  it("copies the raw summary text for summarize_document", () => {
    const call = toolCallMsg("c1", "summarize_document", { document_uid: "doc-1" });
    const result = toolResultMsg("c1", "This document is about...");
    const entries = groupTraceEntries([call, result]);
    expect(toolCopyText(entries[0])).toBe("This document is about...");
  });

  it("copies the uid-stripped tree text for list_document_tree", () => {
    const call = toolCallMsg("c1", "list_document_tree", {});
    const result = toolResultMsg("c1", "report.pdf [doc-1] (2026-01-01)");
    const entries = groupTraceEntries([call, result]);
    expect(toolCopyText(entries[0])).toBe("report.pdf (2026-01-01)");
  });

  it("falls back to the generic {action, status} payload when the tool call has no result yet", () => {
    const call = toolCallMsg("c1", "summarize_document", {});
    const entries = groupTraceEntries([call]);
    expect(JSON.parse(toolCopyText(entries[0]) ?? "")).toEqual({ action: "Summarize Document", status: "running" });
  });
});

// ── groupTraceEntries — deduplication ────────────────────────────────────────

describe("groupTraceEntries deduplication", () => {
  it("collapses duplicate tool_call messages with the same call_id into one row", () => {
    const call1 = toolCallMsg("c1", "search");
    const call1dup = toolCallMsg("c1", "search"); // same call_id, duplicate
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([call1, call1dup, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call: call1, result });
  });

  it("preserves args and result on the surviving combo entry", () => {
    const call = toolCallMsg("c1", "mcp__tavily__web_search", { query: "hello" });
    const callDup = toolCallMsg("c1", "mcp__tavily__web_search", { query: "hello" });
    const result = toolResultMsg("c1", "some result");
    const entries = groupTraceEntries([call, callDup, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("combo");
    if (entries[0].kind === "combo") {
      expect(entries[0].result).toBe(result);
    }
  });

  it("does not collapse tool_calls with different call_ids", () => {
    const call1 = toolCallMsg("c1", "search");
    const call2 = toolCallMsg("c2", "search");
    const entries = groupTraceEntries([call1, call2]);
    expect(entries).toHaveLength(2);
  });
});
