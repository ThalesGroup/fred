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
import type { ChatMessage } from "../../slices/runtime/runtimeOpenApi";
import {
  isAgentTodoSnapshotSettled,
  latestAgentTodoSnapshot,
  parseWriteTodosSnapshot,
  presentAgentTodos,
} from "./agentTodo";

function toolCall(name: string, args: Record<string, unknown>, rank = 0): ChatMessage {
  return {
    session_id: "session-1",
    exchange_id: "exchange-1",
    rank,
    timestamp: "2026-09-17T00:00:00.000Z",
    role: "assistant",
    channel: "tool_call",
    parts: [{ type: "tool_call", call_id: `call-${rank}`, name, args }],
  };
}

function toolResult(callId: string, ok: boolean, rank: number): ChatMessage {
  return {
    session_id: "session-1",
    exchange_id: "exchange-1",
    rank,
    timestamp: "2026-09-17T00:00:00.000Z",
    role: "tool",
    channel: "tool_result",
    parts: [{ type: "tool_result", call_id: callId, ok, content: "", latency_ms: null }],
  };
}

describe("parseWriteTodosSnapshot", () => {
  it("accepts every supported task status and trims task content", () => {
    expect(
      parseWriteTodosSnapshot(
        toolCall("write_todos", {
          todos: [
            { content: " Pending task ", status: "pending" },
            { content: "Active task", status: "in_progress" },
            { content: "Completed task", status: "completed" },
          ],
        }),
      ),
    ).toEqual({
      callId: "call-0",
      todos: [
        { content: "Pending task", status: "pending" },
        { content: "Active task", status: "in_progress" },
        { content: "Completed task", status: "completed" },
      ],
    });
  });

  it.each([
    ["missing todos", {}],
    ["non-array todos", { todos: "task" }],
    ["missing content", { todos: [{ status: "pending" }] }],
    ["empty content", { todos: [{ content: "  ", status: "pending" }] }],
    ["unknown status", { todos: [{ content: "Task", status: "blocked" }] }],
    ["non-object item", { todos: ["Task"] }],
  ])("rejects %s", (_label, args) => {
    expect(parseWriteTodosSnapshot(toolCall("write_todos", args))).toBeNull();
  });

  it("rejects other tool names", () => {
    expect(parseWriteTodosSnapshot(toolCall("write_todo", { todos: [] }))).toBeNull();
  });
});

describe("latestAgentTodoSnapshot", () => {
  it("returns the newest valid full snapshot", () => {
    const first = toolCall("write_todos", { todos: [{ content: "First", status: "pending" }] }, 1);
    const latest = toolCall("write_todos", { todos: [{ content: "Latest", status: "in_progress" }] }, 2);
    expect(latestAgentTodoSnapshot([first, latest])).toEqual({
      callId: "call-2",
      todos: [{ content: "Latest", status: "in_progress" }],
    });
  });

  it("falls back to the last valid snapshot when a later call is malformed", () => {
    const valid = toolCall("write_todos", { todos: [{ content: "Keep", status: "pending" }] }, 1);
    const malformed = toolCall("write_todos", { todos: [{ content: "Broken", status: "unknown" }] }, 2);
    expect(latestAgentTodoSnapshot([valid, malformed])?.todos).toEqual([{ content: "Keep", status: "pending" }]);
  });

  it("falls back to the previous snapshot when a later update fails", () => {
    const previous = toolCall("write_todos", { todos: [{ content: "Keep", status: "pending" }] }, 1);
    const failed = toolCall("write_todos", { todos: [{ content: "Discard", status: "completed" }] }, 2);
    expect(latestAgentTodoSnapshot([previous, failed, toolResult("call-2", false, 3)])).toEqual({
      callId: "call-1",
      todos: [{ content: "Keep", status: "pending" }],
    });
  });

  it("accepts the latest result when a replay replaces an earlier failure", () => {
    const update = toolCall("write_todos", { todos: [{ content: "Keep", status: "pending" }] }, 1);
    expect(latestAgentTodoSnapshot([update, toolResult("call-1", false, 2), toolResult("call-1", true, 3)])).toEqual({
      callId: "call-1",
      todos: [{ content: "Keep", status: "pending" }],
    });
  });

  it("preserves an explicit empty snapshot so the caller can clear the panel", () => {
    const previous = toolCall("write_todos", { todos: [{ content: "Done", status: "completed" }] }, 1);
    expect(latestAgentTodoSnapshot([previous, toolCall("write_todos", { todos: [] }, 2)])).toEqual({
      callId: "call-2",
      todos: [],
    });
  });

  it("returns null when no valid snapshot exists", () => {
    expect(latestAgentTodoSnapshot([toolCall("search", { query: "todos" })])).toBeNull();
  });
});

describe("isAgentTodoSnapshotSettled", () => {
  it("settles a snapshot when the same exchange later emits a final message", () => {
    const call = toolCall("write_todos", { todos: [{ content: "Answer", status: "in_progress" }] }, 1);
    const final: ChatMessage = {
      ...call,
      rank: 2,
      channel: "final",
      parts: [{ type: "text", text: "Done" }],
    };

    expect(isAgentTodoSnapshotSettled([call, final], "call-1")).toBe(true);
  });

  it("does not settle from another exchange", () => {
    const call = toolCall("write_todos", { todos: [{ content: "Answer", status: "in_progress" }] }, 2);
    const otherFinal: ChatMessage = {
      ...call,
      exchange_id: "exchange-2",
      rank: 3,
      channel: "final",
      parts: [{ type: "text", text: "Other answer" }],
    };

    expect(isAgentTodoSnapshotSettled([otherFinal, call], "call-2")).toBe(false);
  });

  it("settles when the authoritative final occupies an earlier array slot", () => {
    const call = toolCall("write_todos", { todos: [{ content: "Answer", status: "in_progress" }] }, 2);
    const final: ChatMessage = {
      ...call,
      rank: 1,
      channel: "final",
      parts: [{ type: "text", text: "Done" }],
    };

    expect(isAgentTodoSnapshotSettled([final, call], "call-2")).toBe(true);
  });

  it("uses the latest replay when call identifiers repeat across exchanges", () => {
    const earlier = toolCall("write_todos", { todos: [{ content: "Earlier", status: "in_progress" }] }, 1);
    const replay = { ...earlier, exchange_id: "exchange-2", rank: 2 };
    const final: ChatMessage = {
      ...replay,
      rank: 3,
      channel: "final",
      parts: [{ type: "text", text: "Done" }],
    };

    expect(isAgentTodoSnapshotSettled([earlier, replay, final], "call-1")).toBe(true);
  });

  it("does not settle a turn that contains a failed tool result", () => {
    const call = toolCall("write_todos", { todos: [{ content: "Answer", status: "in_progress" }] }, 1);
    const failedResult = toolResult("other-call", false, 2);
    const final: ChatMessage = {
      ...call,
      rank: 3,
      channel: "final",
      parts: [{ type: "text", text: "Tool failed" }],
    };

    expect(isAgentTodoSnapshotSettled([call, failedResult, final], "call-1")).toBe(false);
  });
});

describe("presentAgentTodos", () => {
  it("completes only the active step when the turn settles", () => {
    expect(
      presentAgentTodos(
        [
          { content: "Active", status: "in_progress" },
          { content: "Later", status: "pending" },
        ],
        true,
      ),
    ).toEqual([
      { content: "Active", status: "completed" },
      { content: "Later", status: "pending" },
    ]);
  });
});
