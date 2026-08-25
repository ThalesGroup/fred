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

// Marginal token accounting (#2403). The per-message badge used to repeat the
// turn's BILLED total, which re-counts the history once per model call and is
// already summed in the conversation header — a tool-heavy turn read 57 357
// tokens where it had genuinely added ~2 400.

import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import { conversationTokenTotals, marginalTokenUsage, toThreadMessages } from "./toThreadMessages";

function turn(exchangeId: string, contextTokens: number | null, output: number, billedInput: number): ChatMessage[] {
  return [
    {
      exchange_id: exchangeId,
      session_id: "s1",
      rank: 0,
      timestamp: "2026-08-21T00:00:00Z",
      role: "user",
      channel: "final",
      parts: [{ type: "text", text: "q" }],
      metadata: {},
    },
    {
      exchange_id: exchangeId,
      session_id: "s1",
      rank: 1,
      timestamp: "2026-08-21T00:00:01Z",
      role: "assistant",
      channel: "final",
      parts: [{ type: "text", text: "a" }],
      metadata: {
        token_usage: { input_tokens: billedInput, output_tokens: output, total_tokens: billedInput + output },
        ...(contextTokens === null ? {} : { context_tokens: contextTokens }),
      },
    },
  ] as ChatMessage[];
}

describe("marginalTokenUsage", () => {
  it("counts a first turn's whole prompt as new", () => {
    // Nothing was in the context before it — the system prompt and tool
    // schemas genuinely are new, once.
    expect(marginalTokenUsage(16704, { input_tokens: 16704, output_tokens: 836, total_tokens: 17540 }, 0)).toEqual({
      input_tokens: 16704,
      output_tokens: 836,
      total_tokens: 17540,
    });
  });

  it("subtracts the context the previous turn ended on", () => {
    // Field case: billed 57 201 in, but the turn only added 3 238.
    expect(marginalTokenUsage(19942, { input_tokens: 57201, output_tokens: 156, total_tokens: 57357 }, 16704)).toEqual({
      input_tokens: 3238,
      output_tokens: 156,
      total_tokens: 3394,
    });
  });

  it("never lets the tool rows exceed the turn's own new-input figure", () => {
    // The regression that exposed the bad anchor: anchoring on
    // `contextTokens + output` assumed the previous turn's whole output came
    // back in the next prompt. Reasoning tokens are counted in `output_tokens`
    // but dropped from replay (`checkpoint_hygiene.py`), so the anchor
    // overshot and the badge showed 2534 new input tokens above two tool rows
    // reading +2254 and +332 — parts larger than the whole.
    const TURN_1_CONTEXT = 16696;
    const TURN_1_OUTPUT = 175;
    const TURN_2_CONTEXT = 19405;
    const TOOL_GROWTH = 2254 + 332;

    const usage = marginalTokenUsage(
      TURN_2_CONTEXT,
      { input_tokens: 55297, output_tokens: 427, total_tokens: 55724 },
      TURN_1_CONTEXT,
    );

    expect(usage?.input_tokens).toBe(2709);
    expect(usage!.input_tokens).toBeGreaterThan(TOOL_GROWTH);
    // The remainder is the question plus the previous answer as re-sent —
    // small and positive, where the old anchor made it -52.
    expect(usage!.input_tokens - TOOL_GROWTH).toBe(123);
    // Pins the anchor choice itself: adding the previous output back would
    // reintroduce the defect.
    expect(
      marginalTokenUsage(
        TURN_2_CONTEXT,
        { input_tokens: 1, output_tokens: 427, total_tokens: 1 },
        TURN_1_CONTEXT + TURN_1_OUTPUT,
      )!.input_tokens,
    ).toBeLessThan(TOOL_GROWTH);
  });

  it("clamps to zero when trimming left a smaller context than before", () => {
    const usage = marginalTokenUsage(5000, { input_tokens: 9000, output_tokens: 10, total_tokens: 9010 }, 40000);
    expect(usage?.input_tokens).toBe(0);
  });

  it("reports nothing when the previous anchor is unknown", () => {
    // A broken chain must fall back to the billed total, not subtract a
    // stale anchor and understate the turn.
    expect(marginalTokenUsage(19942, { input_tokens: 100, output_tokens: 5, total_tokens: 105 }, null)).toBeNull();
  });

  it("reports nothing when the turn itself has no context anchor", () => {
    expect(marginalTokenUsage(null, { input_tokens: 100, output_tokens: 5, total_tokens: 105 }, 0)).toBeNull();
  });
});

describe("toThreadMessages — marginal usage across a conversation", () => {
  it("chains each turn's anchor to the previous one", () => {
    const messages = [...turn("e1", 16704, 836, 16704), ...turn("e2", 19942, 156, 57201)];

    const assistants = toThreadMessages(messages, false).filter((m) => m.role === "assistant");

    expect(assistants[0].marginalTokenUsage).toEqual({
      input_tokens: 16704,
      output_tokens: 836,
      total_tokens: 17540,
    });
    expect(assistants[1].marginalTokenUsage).toEqual({
      input_tokens: 3238,
      output_tokens: 156,
      total_tokens: 3394,
    });
    // The billed figure stays intact — the conversation header sums it.
    expect(assistants[1].tokenUsage?.total_tokens).toBe(57357);
  });

  it("falls back to the billed total after a turn with no anchor", () => {
    // A Graph-agent turn (or pre-#2403 history) in the middle breaks the
    // chain; the turn after it cannot be measured against a stale anchor.
    const messages = [...turn("e1", 16704, 836, 16704), ...turn("e2", null, 20, 900), ...turn("e3", 30000, 40, 5000)];

    const assistants = toThreadMessages(messages, false).filter((m) => m.role === "assistant");

    expect(assistants[0].marginalTokenUsage).not.toBeNull();
    expect(assistants[1].marginalTokenUsage).toBeNull();
    expect(assistants[2].marginalTokenUsage).toBeNull();
    expect(assistants[2].tokenUsage?.total_tokens).toBe(5040);
  });
});

describe("conversationTokenTotals — the header reconciles with the thread", () => {
  it("sums exactly what the message badges show", () => {
    // Field case: two turns badged 16 871 and 3 136 sat under a header
    // reading 72 595, because the header summed the BILLED usage instead.
    const messages = [...turn("e1", 16696, 175, 16696), ...turn("e2", 19405, 427, 55297)];
    const assistants = toThreadMessages(messages, false).filter((m) => m.role === "assistant");

    const total = conversationTokenTotals(assistants);

    expect(assistants[0].marginalTokenUsage?.total_tokens).toBe(16871);
    expect(assistants[1].marginalTokenUsage?.total_tokens).toBe(3136);
    expect(total.total_tokens).toBe(16871 + 3136);
  });

  it("telescopes to the final context plus every answer produced", () => {
    // Each turn contributes contextTokens(T) - contextTokens(T-1), so the
    // input side collapses to the last context size. That identity is what
    // makes the header a meaningful quantity rather than an arbitrary sum.
    const messages = [...turn("e1", 16696, 175, 16696), ...turn("e2", 19405, 427, 55297)];
    const assistants = toThreadMessages(messages, false).filter((m) => m.role === "assistant");

    const total = conversationTokenTotals(assistants);

    expect(total.input_tokens).toBe(19405);
    expect(total.output_tokens).toBe(175 + 427);
  });

  it("falls back to a turn's billed usage when it has no marginal figure", () => {
    // Otherwise the header would silently omit a message the reader can see.
    const messages = [...turn("e1", null, 20, 900)];
    const assistants = toThreadMessages(messages, false).filter((m) => m.role === "assistant");

    const total = conversationTokenTotals(assistants);

    expect(assistants[0].marginalTokenUsage).toBeNull();
    expect(total.total_tokens).toBe(920);
  });
});
