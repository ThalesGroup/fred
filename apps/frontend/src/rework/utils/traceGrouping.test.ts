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

import { describe, expect, it } from "vitest";
import type { TraceRow } from "./traceUtils";
import { groupTraceRows, type TraceGroupRule } from "./traceGrouping";

const rule: TraceGroupRule = {
  id: "other-tool-family",
  titleKey: "group.title",
  itemKey: "group.item",
  countKey: "group.count",
  matches: (entry) => entry.call.parts?.[0]?.type === "tool_call" && entry.call.parts[0].name === "summarize_document",
  preview: () => "",
};

function row(name: string, id: string, index: number): TraceRow {
  return {
    entry: {
      kind: "combo",
      call: {
        session_id: "s",
        exchange_id: "e",
        rank: index,
        timestamp: "2026-01-01T00:00:00Z",
        role: "assistant",
        channel: "tool_call",
        parts: [{ type: "tool_call", call_id: id, name, args: {} }],
      },
    },
    lane: "step",
    index,
    reasoningText: null,
    reasoningMarkdown: null,
    restated: false,
  };
}

describe("groupTraceRows", () => {
  it("can group another tool family through a rule and renumber visible steps", () => {
    const items = groupTraceRows(
      [
        row("summarize_document", "s1", 1),
        row("summarize_document", "s2", 2),
        row("execute_code", "c1", 3),
        row("summarize_document", "s3", 4),
      ],
      [rule],
    );
    expect(items.map((item) => [item.kind, item.index])).toEqual([
      ["group", 1],
      ["row", 2],
      ["group", 3],
    ]);
    expect(items[0].kind === "group" && items[0].count).toBe(2);
    expect(items[2].kind === "group" && items[2].count).toBe(1);
  });
});
