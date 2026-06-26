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

import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import {
  ALPHA,
  BETA,
  BETA_MARKER,
  CONTEXT_PROMPT_MARKER_BASE,
  fileOf,
  MARKER,
  PROBE,
  PROMPT_PROBE,
  SELF_TEST_AGENT_ID,
  SYSTEM_PROMPT_MARKER_BASE,
} from "./corpus";

/** Run-scoped suffix so fixture folders never collide with (or delete) real user
 * content of the same name, and cleanup targets only the IDs this run created. */
const TOKEN = (globalThis.crypto?.randomUUID?.() ?? `${Math.random()}`).slice(0, 8);
const runName = (base: string) => `${base}-${TOKEN}`;
// Distinct run-scoped markers the agent must echo back, proving each prompt
// delivery path end-to-end (no LLM — the agent echoes verbatim, so it is a
// deterministic "the text arrived" assertion, not "a model obeyed it").
const SYSTEM_MARKER = runName(SYSTEM_PROMPT_MARKER_BASE);
const CONTEXT_MARKER = runName(CONTEXT_PROMPT_MARKER_BASE);

/**
 * Scenario #1 — the live-stack self-test. Validates three user-facing journeys
 * through the REAL execution pipeline, all asserted on the agent's echoed reply:
 *
 *  1. RAG retrieval scope — a marker doc is found when scoped to folder A and
 *     absent when scoped to folder B.
 *  2. System prompt (tuning) — the per-instance `prompts.system` set at enrollment
 *     is delivered to the agent.
 *  3. Context/marketplace prompt — a personal prompt-library prompt attached to a
 *     session is resolved into `context_prompt_text` and delivered to the agent.
 *
 * Fixtures use run-scoped names; only what this run created is deleted at the end.
 */
export const selfTestScenario: Scenario = async (deps, report, signal) => {
  let alpha: string | null = null;
  let beta: string | null = null;
  let agentInstanceId: string | null = null;
  let promptId: string | null = null;
  let sessionId: string | null = null;

  try {
    alpha = await runStep(report, "create-alpha", "Create folder ALPHA", async () => {
      const id = await deps.createLibrary(runName(ALPHA.library));
      return { value: id, detail: `${runName(ALPHA.library)} (${id})` };
    });
    beta = await runStep(report, "create-beta", "Create folder BETA", async () => {
      const id = await deps.createLibrary(runName(BETA.library));
      return { value: id, detail: `${runName(BETA.library)} (${id})` };
    });

    agentInstanceId = await runStep(report, "provision-agent", "Provision the self-test agent", async () => {
      // Enroll with a run-scoped system-prompt marker (the tuning-prompt path).
      const id = await deps.provisionAgentInstance(SELF_TEST_AGENT_ID, { "prompts.system": SYSTEM_MARKER });
      if (!id)
        throw new SkipStep(
          `template '${SELF_TEST_AGENT_ID}' not found — restart the fred-agents pod with the new code`,
        );
      return { value: id, detail: id };
    });

    await runStep(report, "ingest-alpha", "Upload + index document into ALPHA", async () => {
      if (!alpha) throw new SkipStep("ALPHA folder missing");
      await deps.ingestDocument(alpha, fileOf(ALPHA), signal);
      return { value: undefined, detail: ALPHA.fileName };
    });
    await runStep(report, "ingest-beta", "Upload + index document into BETA", async () => {
      if (!beta) throw new SkipStep("BETA folder missing");
      await deps.ingestDocument(beta, fileOf(BETA), signal);
      return { value: undefined, detail: BETA.fileName };
    });

    await runStep(report, "query-alpha", "Ask the agent (ALPHA) — marker must be found", async () => {
      if (!alpha || !agentInstanceId) throw new SkipStep("ALPHA folder or agent instance missing");
      const turn = await deps.runAgentTurn({ agentInstanceId, question: PROBE, libraryIds: [alpha] });
      if (!turn.answer.includes(MARKER)) {
        throw new Error(`marker '${MARKER}' not in the agent answer (${turn.answer.slice(0, 80)}…)`);
      }
      return { value: undefined, detail: `marker retrieved (${turn.sources.length} source(s))` };
    });
    await runStep(report, "query-beta", "Ask the agent (BETA) — B retrieved, A-marker absent", async () => {
      if (!beta || !agentInstanceId) throw new SkipStep("BETA folder or agent instance missing");
      const turn = await deps.runAgentTurn({ agentInstanceId, question: PROBE, libraryIds: [beta] });
      // Absence of MARKER is only meaningful if the B retrieval path actually ran
      // and returned B content — otherwise a non-searchable / over-restricted B
      // library would pass this isolation check having validated nothing.
      if (turn.sources.length === 0 || !turn.answer.includes(BETA_MARKER)) {
        throw new Error(
          `BETA retrieval did not return B content (sources=${turn.sources.length}, '${BETA_MARKER}' ${
            turn.answer.includes(BETA_MARKER) ? "present" : "absent"
          }) — absence of '${MARKER}' is not a valid isolation result`,
        );
      }
      if (turn.answer.includes(MARKER)) throw new Error(`marker '${MARKER}' leaked into the BETA scope`);
      return { value: undefined, detail: `B retrieved (${turn.sources.length} src), A-marker absent` };
    });

    // ── Journey 2: system prompt (tuning) ──────────────────────────────────────
    await runStep(report, "query-system-prompt", "Verify the system prompt (tuning) was delivered", async () => {
      if (!agentInstanceId) throw new SkipStep("agent instance missing");
      // No library / session needed: the tuning prompt is enrollment-scoped.
      const turn = await deps.runAgentTurn({ agentInstanceId, question: PROMPT_PROBE, libraryIds: [] });
      if (!turn.answer.includes(SYSTEM_MARKER)) {
        throw new Error(`system prompt marker '${SYSTEM_MARKER}' not delivered (${turn.answer.slice(-100)})`);
      }
      return { value: undefined, detail: "system prompt echoed back" };
    });

    // ── Journey 3: context/marketplace prompt ──────────────────────────────────
    promptId = await runStep(report, "create-prompt", "Create a personal context prompt", async () => {
      const id = await deps.createContextPrompt(
        runName("fred-selftest-prompt"),
        `Self-test context prompt. Delivery marker: ${CONTEXT_MARKER}`,
      );
      return { value: id, detail: id };
    });
    sessionId = await runStep(report, "create-session", "Create a chat session", async () => {
      if (!agentInstanceId) throw new SkipStep("agent instance missing");
      const id = await deps.createSession(agentInstanceId);
      return { value: id, detail: id };
    });
    await runStep(report, "attach-prompt", "Attach the prompt to the session", async () => {
      if (!sessionId || !promptId) throw new SkipStep("session or prompt missing");
      await deps.attachSessionPrompts(sessionId, [promptId]);
      return { value: undefined, detail: `prompt ${promptId} → session ${sessionId}` };
    });
    await runStep(report, "query-context-prompt", "Verify the marketplace prompt was delivered", async () => {
      if (!agentInstanceId || !sessionId) throw new SkipStep("agent instance or session missing");
      // prepare-execution resolves the session's attached prompts into context_prompt_text.
      const turn = await deps.runAgentTurn({ agentInstanceId, question: PROMPT_PROBE, libraryIds: [], sessionId });
      if (!turn.answer.includes(CONTEXT_MARKER)) {
        throw new Error(`context prompt marker '${CONTEXT_MARKER}' not delivered (${turn.answer.slice(-120)})`);
      }
      return { value: undefined, detail: "marketplace prompt echoed back" };
    });
  } finally {
    // Teardown is `optional`: a skip here means "nothing was created" (an earlier
    // failure), which must not by itself fail an otherwise-clean run. Only the IDs
    // this run created are deleted — never anything matched by name.
    const teardown = { optional: true };
    await runStep(
      report,
      "delete-session",
      "Delete the chat session",
      async () => {
        if (!sessionId) throw new SkipStep("no session was created");
        await deps.deleteSession(sessionId);
        return { value: undefined, detail: `deleted ${sessionId}` };
      },
      teardown,
    );
    await runStep(
      report,
      "delete-prompt",
      "Delete the context prompt",
      async () => {
        if (!promptId) throw new SkipStep("no prompt was created");
        await deps.deleteContextPrompt(promptId);
        return { value: undefined, detail: `deleted ${promptId}` };
      },
      teardown,
    );
    await runStep(
      report,
      "delete-agent",
      "Delete the self-test agent instance",
      async () => {
        if (!agentInstanceId) throw new SkipStep("no instance was provisioned");
        await deps.deleteAgentInstance(agentInstanceId);
        return { value: undefined, detail: `deleted ${agentInstanceId}` };
      },
      teardown,
    );
    await runStep(
      report,
      "delete-alpha",
      "Delete folder ALPHA (cascades its document)",
      async () => {
        if (!alpha) throw new SkipStep("nothing was created");
        await deps.deleteLibrary(alpha);
        return { value: undefined, detail: `deleted ${alpha}` };
      },
      teardown,
    );
    await runStep(
      report,
      "delete-beta",
      "Delete folder BETA (cascades its document)",
      async () => {
        if (!beta) throw new SkipStep("nothing was created");
        await deps.deleteLibrary(beta);
        return { value: undefined, detail: `deleted ${beta}` };
      },
      teardown,
    );
    // Verify deletion actually happened (by the IDs we created, not by name).
    await runStep(
      report,
      "verify-deletion",
      "Verify the fixtures are gone",
      async () => {
        const created = new Set([alpha, beta].filter((id): id is string => id != null));
        if (created.size === 0) throw new SkipStep("nothing was created");
        const ids = new Set((await deps.listLibraries()).map((l) => l.id));
        const remaining = [...created].filter((id) => ids.has(id));
        if (remaining.length) throw new Error(`${remaining.length} fixture folder(s) still present after delete`);
        return { value: undefined, detail: "all created fixtures removed" };
      },
      teardown,
    );
  }
};
