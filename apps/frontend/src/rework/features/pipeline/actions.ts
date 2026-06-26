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

// Hook-free building blocks shared by every scenario. Each one drives the same
// product path the real UI uses: the upload streamer, the ingestion task SSE,
// and the managed-agent execution stream.

import { KeyCloakService } from "../../../security/KeycloakService";
import { streamUploadOrProcessDocument } from "../../../slices/streamDocumentUpload";
import { buildComposerRuntimeContext } from "../../components/pages/ManagedChatPage/runtimeContextBuilder";
import type { AgentTurnResult } from "./types";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

/** What `prepare-execution` returns and `streamAgentTurn` needs from it. */
export interface PreparedExecution {
  execution_grant: unknown;
  execute_stream_url: string;
  context_prompt_text?: string | null;
}

async function bearer(): Promise<string> {
  await KeyCloakService.ensureFreshToken(30);
  return KeyCloakService.GetToken() ?? "";
}

/** Iterate the `data:` JSON frames of an SSE stream. */
async function* sseFrames(body: ReadableStream<Uint8Array>): AsyncGenerator<Record<string, unknown>> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const blocks = buf.split("\n\n");
      buf = blocks.pop() ?? "";
      for (const block of blocks) {
        const line = block.split("\n").find((l) => l.startsWith("data: "));
        const raw = line?.slice(6).trim();
        if (!raw || raw === "[DONE]") continue;
        try {
          yield JSON.parse(raw) as Record<string, unknown>;
        } catch {
          // ignore non-JSON frames (heartbeats, comments)
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** Upload a document into a library and return the scheduled ingestion task id. */
export async function uploadDocument(libraryId: string, file: File): Promise<string> {
  const tasks = await streamUploadOrProcessDocument(file, "process", { tags: [libraryId], profile: "fast" });
  const taskId = tasks[0]?.taskId;
  if (!taskId) throw new Error(`upload of ${file.name} returned no ingestion task`);
  return taskId;
}

/** Wait on the real ingestion task SSE until the document is indexed (succeeded). */
export async function awaitIngestion(taskId: string, signal: AbortSignal): Promise<void> {
  const response = await fetch(`/knowledge-flow/v1/tasks/${taskId}/events`, {
    headers: { Authorization: `Bearer ${await bearer()}`, Accept: "text/event-stream" },
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`ingestion task ${taskId}: HTTP ${response.status}`);
  for await (const event of sseFrames(response.body)) {
    const state = event.state;
    if (typeof state === "string" && TERMINAL.has(state)) {
      if (state !== "succeeded") throw new Error(`ingestion ${state}: ${event.error ?? "unknown error"}`);
      return;
    }
  }
  throw new Error(`ingestion task ${taskId} ended without a terminal state`);
}

/** Run one managed-agent turn through the real execution pipeline; collect the final answer + sources. */
export async function streamAgentTurn(
  prep: PreparedExecution,
  args: { agentInstanceId: string; question: string; libraryIds: string[]; sessionId?: string | null },
): Promise<AgentTurnResult> {
  const runtimeContext = buildComposerRuntimeContext({
    selectedLibraryIds: args.libraryIds,
    selectedDocumentUids: [],
    searchPolicy: "hybrid",
    ragScope: "corpus_only",
  });

  const response = await fetch(prep.execute_stream_url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${await bearer()}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      agent_instance_id: args.agentInstanceId,
      execution_grant: prep.execution_grant,
      input: args.question,
      session_id: args.sessionId ?? null,
      runtime_context: {
        ...runtimeContext,
        ...(prep.context_prompt_text != null ? { context_prompt_text: prep.context_prompt_text } : {}),
      },
    }),
  });
  if (!response.ok || !response.body) throw new Error(`agent execution: HTTP ${response.status}`);

  let answer = "";
  let sources: unknown[] = [];
  let sessionId = args.sessionId ?? null;
  let sawFinal = false;
  let runtimeError: string | null = null;
  for await (const event of sseFrames(response.body)) {
    if (event.kind === "final") {
      sawFinal = true;
      answer = typeof event.content === "string" ? event.content : "";
      sources = Array.isArray(event.sources) ? event.sources : [];
      if (typeof event.session_id === "string") sessionId = event.session_id;
    } else if (event.kind === "execution_error" || event.kind === "node_error" || event.kind === "error") {
      // A runtime failure must never pass as an empty answer (e.g. the BETA
      // "marker absent" check would otherwise go falsely green).
      runtimeError =
        (typeof event.error === "string" && event.error) ||
        (typeof event.message === "string" && event.message) ||
        (typeof event.content === "string" && event.content) ||
        `runtime ${event.kind}`;
    }
  }
  if (runtimeError) throw new Error(`agent execution failed: ${runtimeError}`);
  if (!sawFinal) throw new Error("agent execution produced no final answer");
  return { answer, sources, sessionId };
}
