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
import {
  mergeContextPromptText,
  mergeReasoningActivation,
  mergeRoutingPolicy,
  parseSseFrames,
} from "../../core/utils/runtimeStream";
import { buildComposerRuntimeContext } from "../../components/pages/ManagedChatPage/runtimeContextBuilder";
import type { ExecutionPreparation } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { RuntimeExecuteRequest } from "../../../slices/runtime/runtimeOpenApi";
import { MAX_HOLD_SECONDS, type AgentTurnResult } from "./types";
import type { CapturedCredential } from "./sessionCredential";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

/** The execute-stream POST was refused outright: the turn never started, so
 * nothing that happened later can be read into it. */
export class AgentTurnRejectedError extends Error {
  readonly status: number;
  constructor(status: number) {
    super(`agent execution: HTTP ${status}`);
    this.status = status;
  }
}

// The harness agent's three fixed verdicts for a call made as the person. Each
// reaches the caller bare on an error event, or wrapped by a final event.
const CREDENTIAL_EXPIRED = "credential expired during protected call";
const PROTECTED_CALL_REFUSED = "protected call refused";
const PROTECTED_CALL_FAILED = "protected call failed";

function isVerdict(message: string, verdict: string): boolean {
  return message === verdict || message === `An error occurred: ${verdict}`;
}

export function isCredentialExpiryFailure(message: string): boolean {
  return isVerdict(message, CREDENTIAL_EXPIRED);
}

export function isProtectedCallRefusal(message: string): boolean {
  return isVerdict(message, PROTECTED_CALL_REFUSED);
}

export function isProtectedCallUnreachable(message: string): boolean {
  return isVerdict(message, PROTECTED_CALL_FAILED);
}

export class AgentTurnExecutionError extends Error {
  constructor(
    readonly statusSeenAt: Record<string, number>,
    readonly credentialExpired = false,
  ) {
    super("agent execution failed");
  }
}

async function bearer(): Promise<string> {
  await KeyCloakService.ensureFreshToken(30);
  return KeyCloakService.GetToken() ?? "";
}

/** Upload a document into a library and return the scheduled ingestion task id. */
export async function uploadDocument(libraryId: string, file: File): Promise<string> {
  const tasks = await streamUploadOrProcessDocument([file], "process", { tags: [libraryId], profile: "fast" });
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
  for await (const event of parseSseFrames(response.body)) {
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
  prep: ExecutionPreparation,
  args: {
    agentInstanceId: string;
    teamId: string;
    question: string;
    libraryIds: string[];
    sessionId?: string | null;
    /** Stream on this captured credential rather than the caller's session. */
    bearer?: CapturedCredential;
    signal?: AbortSignal;
    onProgress?: (detail: string) => void;
    /** Called as each named status arrives, so a long turn can report what it
     *  has already proven instead of only at the end. */
    onStatus?: (status: string) => void;
  },
): Promise<AgentTurnResult> {
  args.signal?.throwIfAborted();
  const runtimeContext = buildComposerRuntimeContext({
    selectedLibraryIds: args.libraryIds,
    selectedDocumentUids: [],
    searchPolicy: "hybrid",
    ragScope: "corpus_only",
  });

  // RUNTIME-07 rev. 2: pod authorizes on runtime_context.team_id (no grant).
  // Typed against the generated contract so any drift is a compile error.
  const body: RuntimeExecuteRequest = {
    agent_instance_id: args.agentInstanceId,
    input: args.question,
    session_id: args.sessionId ?? null,
    runtime_context: mergeReasoningActivation(
      mergeRoutingPolicy(
        mergeContextPromptText({ ...runtimeContext, team_id: args.teamId }, prep.context_prompt_text),
        prep.chat_default_profile_id,
        prep.agent_profile_overrides,
      ),
      prep.reasoning_enabled_model_ids,
    ),
  };

  const response = await fetch(prep.execute_stream_url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${args.bearer ?? (await bearer())}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal: args.signal,
  });
  if (!response.ok) throw new AgentTurnRejectedError(response.status);
  if (!response.body) throw new AgentTurnExecutionError({});

  let answer = "";
  let sources: unknown[] = [];
  let sessionId = args.sessionId ?? null;
  let sawFinal = false;
  let runtimeError: string | null = null;
  const statusSeenAt: Record<string, number> = {};
  try {
    for await (const event of parseSseFrames(response.body)) {
      args.signal?.throwIfAborted();
      if (event.kind === "status") {
        if (typeof event.status === "string") {
          statusSeenAt[event.status] = Date.now();
          args.onStatus?.(event.status);
        }
      } else if (event.kind === "thought_delta" && typeof event.delta === "string") {
        // Display only the bounded diagnostic progress, never arbitrary tool text.
        const hold = /^holding (\d{1,3})\/(\d{1,3}) s before retrieval$/.exec(event.delta);
        if (hold && Number(hold[1]) <= Number(hold[2]) && Number(hold[2]) <= MAX_HOLD_SECONDS) {
          args.onProgress?.(event.delta);
        }
      } else if (event.kind === "final") {
        sawFinal = true;
        answer = typeof event.content === "string" ? event.content : "";
        sources = Array.isArray(event.sources) ? event.sources : [];
        if (typeof event.session_id === "string") sessionId = event.session_id;
      } else if (event.kind === "execution_error" || event.kind === "node_error" || event.kind === "error") {
        // A runtime failure must never pass as an empty answer (e.g. the BETA
        // "marker absent" check would otherwise go falsely green).
        runtimeError =
          (typeof event.error === "string" && event.error) ||
          (typeof event.error_message === "string" && event.error_message) ||
          (typeof event.message === "string" && event.message) ||
          (typeof event.content === "string" && event.content) ||
          `runtime ${event.kind}`;
      }
    }
  } catch {
    args.signal?.throwIfAborted();
    throw new AgentTurnExecutionError(statusSeenAt);
  }
  args.signal?.throwIfAborted();
  if (runtimeError) throw new AgentTurnExecutionError(statusSeenAt, isCredentialExpiryFailure(runtimeError));
  if (!sawFinal) throw new AgentTurnExecutionError(statusSeenAt);
  return { answer, sources, sessionId, statusSeenAt };
}
