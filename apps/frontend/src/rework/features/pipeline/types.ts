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

// A small engine for running a sequence of REAL product actions (create a
// folder, ingest a document, run an agent turn, …) and reporting each step.
// The self-test campaign is one scenario; seeding a team with a corpus and
// conversations to demo the evaluation dataset builder is another — both
// compose the same PipelineDeps actions.

export type StepStatus = "pending" | "running" | "passed" | "failed" | "skipped";

export interface StepReport {
  id: string;
  title: string;
  status: StepStatus;
  detail?: string;
  error?: string;
  durationMs?: number;
  /** Teardown/optional steps may legitimately skip; a skipped REQUIRED step (default) means
   * the run did not actually validate what it set out to, so it must not read as success. */
  optional?: boolean;
}

export type Reporter = (step: StepReport) => void;

/** The answer of one agent turn, plus the (optionally persisted) conversation. */
export interface AgentTurnResult {
  answer: string;
  sources: unknown[];
  sessionId: string | null;
}

/**
 * The reusable building blocks, each backed by the same product API the real UI
 * uses. Scenarios depend only on this contract; `usePipelineRun` provides it.
 */
export interface PipelineDeps {
  teamId: string;
  createLibrary(name: string): Promise<string>;
  deleteLibrary(libraryId: string): Promise<void>;
  /** List the caller's document libraries (for reconcile-before-create and verify-after-delete). */
  listLibraries(): Promise<Array<{ id: string; name: string }>>;
  /** Upload a document and wait for the real ingestion task to finish indexing it. */
  ingestDocument(libraryId: string, file: File, signal: AbortSignal): Promise<void>;
  /** Enroll a fresh managed instance of an agent template, optionally with initial tuning
   * field values (e.g. a system prompt). Null if the template isn't available. */
  provisionAgentInstance(
    sourceAgentId: string,
    tuningFieldValues?: Record<string, string | number | boolean>,
  ): Promise<string | null>;
  /** Delete a managed agent instance (teardown). */
  deleteAgentInstance(agentInstanceId: string): Promise<void>;
  /** Create a personal prompt-library prompt and return its id (the marketplace-prompt path). */
  createContextPrompt(name: string, text: string): Promise<string>;
  /** Delete a prompt-library prompt (teardown). */
  deleteContextPrompt(promptId: string): Promise<void>;
  /** Create a chat session bound to an agent instance and return its id. */
  createSession(agentInstanceId: string): Promise<string>;
  /** Attach (replace) the set of context prompts on a session — resolved into
   * `context_prompt_text` at prepare-execution. */
  attachSessionPrompts(sessionId: string, promptIds: string[]): Promise<void>;
  /** Delete a chat session (teardown). */
  deleteSession(sessionId: string): Promise<void>;
  /** Run one real agent turn through the execution pipeline. Persists a conversation when sessionId is set. */
  runAgentTurn(args: {
    agentInstanceId: string;
    question: string;
    libraryIds: string[];
    sessionId?: string | null;
  }): Promise<AgentTurnResult>;
}

/** A scenario composes actions and reports each step. */
export type Scenario = (deps: PipelineDeps, report: Reporter, signal: AbortSignal) => Promise<void>;
