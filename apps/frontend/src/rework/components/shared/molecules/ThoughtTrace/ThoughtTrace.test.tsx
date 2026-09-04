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

// ThoughtTrace: one chronological sequence. Reasoning still renders differently
// from a tool step (#2172), but the two now alternate in arrival order rather
// than being stacked into a reasoning lane above a tool lane.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import { ThoughtTrace } from "./ThoughtTrace";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <span data-icon={type} />,
}));

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

/** The screenshot case: one model-native reasoning block, then two identical tool calls. */
const REASONING: ChatMessage = msg({
  channel: "thought",
  parts: [{ type: "text", text: "I should list the tabular documents first" }],
  metadata: {
    extras: {
      thought_id: "t1",
      phase: "planning",
      title: "Model reasoning",
      source: "model_native",
      duration_ms: 16400,
    },
  },
});

const TRACE: ChatMessage[] = [
  REASONING,
  msg({ channel: "tool_call", parts: [{ type: "tool_call", call_id: "c1", name: "read_query", args: {} }] }),
  msg({
    channel: "tool_result",
    role: "tool",
    parts: [
      {
        type: "tool_result",
        call_id: "c1",
        ok: true,
        content: JSON.stringify({ sql_query: "SELECT 1", rows: [{ a: 1 }, { a: 2 }] }),
        latency_ms: 258,
      },
    ],
  }),
  msg({ channel: "tool_call", parts: [{ type: "tool_call", call_id: "c2", name: "read_query", args: {} }] }),
  msg({
    channel: "tool_result",
    role: "tool",
    parts: [{ type: "tool_result", call_id: "c2", ok: true, content: "opaque", latency_ms: 310 }],
  }),
];

function render(messages: ChatMessage[], done: boolean, pendingToolCallIds?: readonly string[] | null): string {
  return renderToStaticMarkup(<ThoughtTrace messages={messages} done={done} pendingToolCallIds={pendingToolCallIds} />);
}

describe("ThoughtTrace", () => {
  it("renders nothing when the turn has no trace", () => {
    expect(render([], true)).toBe("");
  });

  it("renders reasoning as its own row, not as a tool step row", () => {
    const html = render(TRACE, false);
    // Only the two tool steps are step rows; the reasoning row is a <button>.
    expect(html.match(/role="button"/g)).toHaveLength(2);
    // Its marker is the settings glyph, and it carries no phase label: the row
    // shows the reasoning itself, not a name for the kind of reasoning it is.
    expect(html).toContain('data-icon="settings"');
    expect(html).not.toContain("rework.chatTrace.phase.");
  });

  it("keeps reasoning and tool steps in the order they happened", () => {
    const second = msg({
      channel: "thought",
      rank: 5,
      parts: [{ type: "text", text: "the first query came back empty" }],
      metadata: { extras: { thought_id: "t2", phase: "reflection", source: "model_native" } },
    });
    // Reasoning, tool, reasoning, tool — as streamed. The old two-lane split
    // hoisted both thoughts above both tools, an order that never occurred.
    const html = render([...TRACE.slice(0, 3), second, ...TRACE.slice(3)], false);

    const order = [...html.matchAll(/I should list|the first query|>1<|>2</g)].map((m) => m[0]);
    expect(order).toEqual(["I should list", ">1<", "the first query", ">2<"]);
  });

  it("numbers the two identical tool calls so they can be told apart", () => {
    const html = render(TRACE, false);
    expect(html).toContain(">1<");
    expect(html).toContain(">2<");
    // …and the recognized result shape adds a curated volume discriminator.
    expect(html).toContain("rework.chatTrace.rows");
  });

  it("shows real execution latency per step", () => {
    const html = render(TRACE, false);
    expect(html).toContain("258ms");
    expect(html).toContain("310ms");
  });

  it("collapses to the summary line alone once the turn is done", () => {
    const html = render(TRACE, true);
    expect(html).not.toContain("rework.chatTrace.phase.planning");
    expect(html).not.toContain("258ms");
    expect(html).toContain("rework.chatTrace.summaryReasoning");
  });

  // A HITL-gated tool call streams as a `tool_call` with no result, exactly
  // like a genuinely in-flight one, well before the human answers the
  // "Confirm tool execution" prompt (the backend commits the model's
  // tool_calls in a step earlier than the HITL gate's own interrupt()) — the
  // row and header must not read "running" while the prompt is still
  // unanswered.
  const PENDING_TOOL_CALL: ChatMessage = msg({
    channel: "tool_call",
    parts: [{ type: "tool_call", call_id: "c3", name: "summarize_document", args: {} }],
  });

  it("renders a HITL-gated call as awaiting confirmation, not as a running step", () => {
    const html = render([PENDING_TOOL_CALL], false, ["c3"]);
    expect(html).toContain("rework.chatTrace.awaitingConfirmation");
    expect(html).toContain('aria-label="awaiting_confirmation"');
    expect(html).not.toContain("rework.chatTrace.running");
    expect(html).not.toContain('aria-label="pending"');
  });

  it("still renders a call as plain running when a DIFFERENT call is the one awaiting confirmation", () => {
    const html = render([PENDING_TOOL_CALL], false, ["some-other-call-id"]);
    expect(html).toContain("rework.chatTrace.running");
    expect(html).toContain('aria-label="pending"');
    expect(html).not.toContain("rework.chatTrace.awaitingConfirmation");
  });

  it("renders a call as plain running when no call is pending confirmation at all", () => {
    const html = render([PENDING_TOOL_CALL], false, null);
    expect(html).toContain("rework.chatTrace.running");
    expect(html).not.toContain("rework.chatTrace.awaitingConfirmation");
  });

  // #2177: a single HITL prompt can gate several document summaries at once
  // (e.g. "summarize this whole folder") — every one of them must read as
  // awaiting confirmation simultaneously, not just the first.
  it("renders EVERY call in a batched HITL prompt as awaiting confirmation, not just one", () => {
    const batch: ChatMessage[] = [
      msg({
        channel: "tool_call",
        parts: [{ type: "tool_call", call_id: "b1", name: "summarize_document", args: {} }],
      }),
      msg({
        channel: "tool_call",
        parts: [{ type: "tool_call", call_id: "b2", name: "summarize_document", args: {} }],
      }),
    ];
    const html = render(batch, false, ["b1", "b2"]);
    expect(html.match(/aria-label="awaiting_confirmation"/g)).toHaveLength(2);
    expect(html).not.toContain('aria-label="pending"');
  });
});
