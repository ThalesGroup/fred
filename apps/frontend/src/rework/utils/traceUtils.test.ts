import { describe, it, expect } from "vitest";
import type { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import {
  formatLatencyMs,
  groupTraceEntries,
  humanizeToolName,
  isTraceChannel,
  isFinalChannel,
  primaryTextForEntry,
  secondaryTextForEntry,
  statusForEntry,
  textOf,
  thoughtSummaryLabel,
  totalLatencyMs,
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
  extras: { streaming_delta?: boolean; title?: string; conclusion?: string; phase?: string } = {},
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

// ── thoughtSummaryLabel ───────────────────────────────────────────────────────

describe("thoughtSummaryLabel", () => {
  it("returns 'Thought…' when there is no latency", () => {
    expect(thoughtSummaryLabel([])).toBe("Thought…");
  });

  it("includes formatted duration when latency is present", () => {
    const entries = [
      { kind: "combo" as const, call: toolCallMsg("c1", "a"), result: toolResultMsg("c1", "r", true, 1500) },
    ];
    expect(thoughtSummaryLabel(entries)).toBe("Thought for 1.5s");
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
