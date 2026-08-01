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

// ThoughtTrace × two lanes (#2172): reasoning must render as its own card, not
// as row #1 of the tool pile, and the whole block must be hideable.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../../slices/agentic/agenticOpenApi";
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

function render(messages: ChatMessage[], done: boolean): string {
  return renderToStaticMarkup(<ThoughtTrace messages={messages} done={done} />);
}

describe("ThoughtTrace", () => {
  it("renders nothing when the turn has no trace", () => {
    expect(render([], true)).toBe("");
  });

  it("renders reasoning as its own card, not as a tool step row", () => {
    const html = render(TRACE, false);
    // Only the two tool steps are step rows; the reasoning card is a <button>.
    expect(html.match(/role="button"/g)).toHaveLength(2);
    expect(html).toContain("rework.chatTrace.phase.planning");
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
});
