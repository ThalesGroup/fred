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

import type { ChatMessage, ToolCallPart, ToolResultPart } from "../../slices/runtime/runtimeOpenApi";

export const WRITE_TODOS_TOOL_NAME = "write_todos";

export type AgentTodoStatus = "pending" | "in_progress" | "completed";

export interface AgentTodo {
  content: string;
  status: AgentTodoStatus;
}

export interface AgentTodoSnapshot {
  callId: string;
  todos: AgentTodo[];
}

const TODO_STATUSES: ReadonlySet<string> = new Set(["pending", "in_progress", "completed"]);

function toolCallPart(message: ChatMessage): ToolCallPart | null {
  const part = message.parts?.[0];
  return message.channel === "tool_call" && part?.type === "tool_call" ? (part as ToolCallPart) : null;
}

function toolResultPart(message: ChatMessage): ToolResultPart | null {
  const part = message.parts?.[0];
  return message.channel === "tool_result" && part?.type === "tool_result" ? (part as ToolResultPart) : null;
}

/** Call IDs whose latest explicit result reports that the tool did not commit its update. */
export function failedToolCallIds(messages: readonly ChatMessage[]): ReadonlySet<string> {
  const resultByCallId = new Map<string, boolean | null | undefined>();
  for (const message of messages) {
    const result = toolResultPart(message);
    if (result?.call_id) resultByCallId.set(result.call_id, result.ok);
  }
  return new Set([...resultByCallId].filter(([, ok]) => ok === false).map(([callId]) => callId));
}

function parseTodo(value: unknown): AgentTodo | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.content !== "string" || candidate.content.trim().length === 0) return null;
  if (typeof candidate.status !== "string" || !TODO_STATUSES.has(candidate.status)) return null;
  return {
    content: candidate.content.trim(),
    status: candidate.status as AgentTodoStatus,
  };
}

/** Returns the complete snapshot carried by one supported `write_todos` call. */
export function parseWriteTodosSnapshot(message: ChatMessage): AgentTodoSnapshot | null {
  const part = toolCallPart(message);
  if (!part || part.name !== WRITE_TODOS_TOOL_NAME || !Array.isArray(part.args?.todos)) return null;

  const todos: AgentTodo[] = [];
  for (const value of part.args.todos) {
    const todo = parseTodo(value);
    if (!todo) return null;
    todos.push(todo);
  }

  return { callId: part.call_id, todos };
}

/** Latest valid full snapshot wins; malformed later calls leave the last usable plan intact. */
export function latestAgentTodoSnapshot(messages: readonly ChatMessage[]): AgentTodoSnapshot | null {
  const failedCallIds = failedToolCallIds(messages);
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const snapshot = parseWriteTodosSnapshot(messages[index]);
    if (snapshot && !failedCallIds.has(snapshot.callId)) return snapshot;
  }
  return null;
}

/** A successful final frame in the same exchange closes the active step for presentation. */
export function isAgentTodoSnapshotSettled(messages: readonly ChatMessage[], callId: string): boolean {
  let callIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (parseWriteTodosSnapshot(messages[index])?.callId === callId) {
      callIndex = index;
      break;
    }
  }
  if (callIndex < 0) return false;
  const exchangeId = messages[callIndex].exchange_id;
  let hasFinal = false;
  for (const message of messages) {
    if (message.exchange_id !== exchangeId) continue;
    if (message.channel === "error" || toolResultPart(message)?.ok === false) return false;
    if (message.role === "assistant" && message.channel === "final") hasFinal = true;
  }
  return hasFinal;
}

/** Finalized turns present their residual active step as complete without mutating stored history. */
export function presentAgentTodos(todos: readonly AgentTodo[], isSettled: boolean): AgentTodo[] {
  return todos.map((todo) =>
    isSettled && todo.status === "in_progress" ? { ...todo, status: "completed" as const } : todo,
  );
}
