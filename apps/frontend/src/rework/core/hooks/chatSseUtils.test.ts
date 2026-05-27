import { describe, it, expect } from "vitest";
import type { ChatMessage } from "../../../slices/agentic/agenticOpenApi";
import {
  keyOf,
  exchangeKeyOf,
  isOptimisticUserMessage,
  hasStreamingDeltaFlag,
  shouldClearStreamingDeltas,
  sortMessages,
  upsertOne,
} from "./chatSseUtils";

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

function streamingMsg(text: string, rank = 0): ChatMessage {
  return msg({
    rank,
    parts: [{ type: "text", text }],
    metadata: { extras: { streaming_delta: true } },
  });
}

function optimisticUser(text: string): ChatMessage {
  return msg({
    role: "user",
    channel: "final",
    parts: [{ type: "text", text }],
    metadata: { extras: { optimistic_user: true } },
  });
}

// ── keyOf / exchangeKeyOf ─────────────────────────────────────────────────────

describe("keyOf", () => {
  it("produces a composite key from all five fields", () => {
    const m = msg({});
    expect(keyOf(m)).toBe("s1|e1|0|assistant|final");
  });

  it("two messages with different rank have different keys", () => {
    expect(keyOf(msg({ rank: 0 }))).not.toBe(keyOf(msg({ rank: 1 })));
  });
});

describe("exchangeKeyOf", () => {
  it("returns session_id|exchange_id", () => {
    expect(exchangeKeyOf(msg({}))).toBe("s1|e1");
  });
});

// ── isOptimisticUserMessage ───────────────────────────────────────────────────

describe("isOptimisticUserMessage", () => {
  it("returns true for an optimistic user message", () => {
    expect(isOptimisticUserMessage(optimisticUser("hi"))).toBe(true);
  });

  it("returns false for a non-optimistic user message", () => {
    expect(isOptimisticUserMessage(msg({ role: "user", channel: "final" }))).toBe(false);
  });

  it("returns false for an assistant message even with the flag", () => {
    const m = msg({ role: "assistant", metadata: { extras: { optimistic_user: true } } });
    expect(isOptimisticUserMessage(m)).toBe(false);
  });
});

// ── hasStreamingDeltaFlag ─────────────────────────────────────────────────────

describe("hasStreamingDeltaFlag", () => {
  it("returns true for a streaming assistant final message", () => {
    expect(hasStreamingDeltaFlag(streamingMsg("chunk"))).toBe(true);
  });

  it("returns false when streaming_delta is absent", () => {
    expect(hasStreamingDeltaFlag(textMsg("complete"))).toBe(false);
  });

  it("returns false for a user message with the flag", () => {
    const m = msg({ role: "user", metadata: { extras: { streaming_delta: true } } });
    expect(hasStreamingDeltaFlag(m)).toBe(false);
  });
});

// ── shouldClearStreamingDeltas ────────────────────────────────────────────────

describe("shouldClearStreamingDeltas", () => {
  it("returns truthy for tool_call", () => {
    expect(shouldClearStreamingDeltas(msg({ channel: "tool_call" }))).toBeTruthy();
  });

  it("returns truthy for tool_result", () => {
    expect(shouldClearStreamingDeltas(msg({ channel: "tool_result" }))).toBeTruthy();
  });

  it("returns truthy for a non-streaming assistant final", () => {
    expect(shouldClearStreamingDeltas(textMsg("done"))).toBeTruthy();
  });

  it("returns falsy for a streaming delta frame", () => {
    expect(shouldClearStreamingDeltas(streamingMsg("partial"))).toBeFalsy();
  });
});

// ── sortMessages ──────────────────────────────────────────────────────────────

describe("sortMessages", () => {
  it("sorts by rank ascending", () => {
    const a = msg({ rank: 2 });
    const b = msg({ rank: 0 });
    const c = msg({ rank: 1 });
    const sorted = sortMessages([a, b, c]);
    expect(sorted.map((m) => m.rank)).toEqual([0, 1, 2]);
  });

  it("breaks rank ties by timestamp ascending", () => {
    const early = msg({ rank: 0, timestamp: "2026-01-01T00:00:00.000Z" });
    const late = msg({ rank: 0, timestamp: "2026-01-01T00:01:00.000Z" });
    const sorted = sortMessages([late, early]);
    expect(sorted[0]).toBe(early);
  });

  it("does not mutate the input array", () => {
    const arr = [msg({ rank: 1 }), msg({ rank: 0 })];
    const original = [...arr];
    sortMessages(arr);
    expect(arr[0]).toBe(original[0]);
  });
});

// ── upsertOne ─────────────────────────────────────────────────────────────────

describe("upsertOne — insert", () => {
  it("inserts a new message when list is empty", () => {
    const m = textMsg("hello");
    expect(upsertOne([], m)).toHaveLength(1);
  });

  it("inserts a new message without touching existing ones", () => {
    const existing = textMsg("existing", { rank: 0 });
    const newMsg = textMsg("new", { rank: 1 });
    const result = upsertOne([existing], newMsg);
    expect(result).toHaveLength(2);
  });

  it("keeps the array sorted after insert", () => {
    const hi = textMsg("hi", { rank: 5 });
    const lo = textMsg("lo", { rank: 0 });
    const result = upsertOne([hi], lo);
    expect(result[0].rank).toBe(0);
    expect(result[1].rank).toBe(5);
  });
});

describe("upsertOne — replace (same key)", () => {
  it("replaces a message with the same composite key", () => {
    const orig = textMsg("v1");
    const updated = textMsg("v2");
    const result = upsertOne([orig], updated);
    expect(result).toHaveLength(1);
    expect((result[0].parts[0] as { text: string }).text).toBe("v2");
  });
});

describe("upsertOne — streaming delta accumulation", () => {
  it("appends text from a streaming delta onto an existing streaming message", () => {
    const first = streamingMsg("Hello");
    const state = upsertOne([], first);
    const second = streamingMsg(", world");
    const result = upsertOne(state, second);
    expect(result).toHaveLength(1);
    expect((result[0].parts[0] as { text: string }).text).toBe("Hello, world");
  });

  it("removes streaming deltas when an authoritative assistant final arrives", () => {
    const delta1 = streamingMsg("chunk1");
    const delta2 = streamingMsg("chunk2");
    let state = upsertOne([], delta1);
    state = upsertOne(state, delta2);
    // Authoritative (non-streaming) final for the same exchange
    const authoritative = textMsg("Full response");
    const result = upsertOne(state, authoritative);
    expect(result).toHaveLength(1);
    expect((result[0].parts[0] as { text: string }).text).toBe("Full response");
    expect(result[0].metadata?.extras).toBeUndefined();
  });

  it("removes streaming deltas when a tool_call arrives in the same exchange", () => {
    const delta = streamingMsg("partial");
    const state = upsertOne([], delta);
    const toolCall = msg({ channel: "tool_call", rank: 1 });
    const result = upsertOne(state, toolCall);
    // streaming delta removed; only the tool_call remains
    expect(result).toHaveLength(1);
    expect(result[0].channel).toBe("tool_call");
  });

  it("does not remove streaming deltas from a different exchange", () => {
    const delta = streamingMsg("partial");
    const state = upsertOne([], delta);
    // authoritative final from a DIFFERENT exchange
    const otherFinal = textMsg("other", { exchange_id: "e99" });
    const result = upsertOne(state, otherFinal);
    // delta kept, other final added
    expect(result).toHaveLength(2);
  });
});

describe("upsertOne — optimistic user message replacement", () => {
  it("replaces an optimistic user message with the server-confirmed version", () => {
    const optimistic = optimisticUser("hello");
    const state = upsertOne([], optimistic);
    // Confirmed message: same session/exchange/role/channel but without the flag
    const confirmed = msg({ role: "user", channel: "final", parts: [{ type: "text", text: "hello" }] });
    const result = upsertOne(state, confirmed);
    expect(result).toHaveLength(1);
    expect(isOptimisticUserMessage(result[0])).toBe(false);
  });

  it("does not confuse optimistic messages from different exchanges", () => {
    const opt1 = optimisticUser("q1");
    const opt2 = msg({
      role: "user",
      channel: "final",
      exchange_id: "e2",
      parts: [{ type: "text", text: "q2" }],
      metadata: { extras: { optimistic_user: true } },
    });
    let state = upsertOne([], opt1);
    state = upsertOne(state, opt2);
    expect(state).toHaveLength(2);
  });
});
