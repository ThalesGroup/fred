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
import { describeError, runStep, SkipStep } from "../step";
import type { PipelineDeps, Scenario } from "../types";
import { CONTEXT_PROMPT_MARKER_BASE, PROMPT_PROBE, SELF_TEST_AGENT_ID, SYSTEM_PROMPT_MARKER_BASE } from "./corpus";
import { cleanup, newRunScope, statusOf } from "./runScope";

export const REPEATED_TURNS = 3;
export const CONCURRENT_SESSIONS = 4;

export interface CopyOutcome {
  agentId: string | null;
  name: string | null;
  errorCode: string | null;
}

export interface AgentsDeps extends PipelineDeps {
  updateAgent: (id: string, change: { system?: string; enabled?: boolean }) => Promise<void>;
  listAgents: () => Promise<Array<{ id: string; name: string }>>;
  effectiveModel: (id: string) => Promise<{ name: string | null; usable: boolean }>;
  copyTargets: (id: string) => Promise<Array<{ teamId: string; templateEnabled: boolean }>>;
  /** Duplicate into the source team; with no name the platform picks a free one. */
  duplicate: (id: string, name?: string) => Promise<CopyOutcome>;
}

/** Agents family: run-scoped instances of the deterministic agent, which echoes the prompts it receives. */
export const agentsScenario: Scenario<AgentsDeps> = async (deps, report, signal) => {
  const scope = newRunScope();
  const firstMarker = scope.name(`${SYSTEM_PROMPT_MARKER_BASE}A`);
  const secondMarker = scope.name(`${SYSTEM_PROMPT_MARKER_BASE}B`);
  const duplicateName = scope.name("Self-test duplicate");
  // The prompt the agent holds now, so a failed update cannot fail later checks too.
  let currentMarker = firstMarker;
  let agentId: string | null = null;
  const copies: string[] = [];
  let nameTaken = false;
  const sessions: string[] = [];
  const prompts: string[] = [];

  const turn = (id: string, sessionId?: string) =>
    deps.runAgentTurn({ agentInstanceId: id, question: PROMPT_PROBE, libraryIds: [], sessionId, signal });

  try {
    agentId = await runStep(report, "provision-agent", "Provision the self-test agent", async () => {
      const id = await deps.provisionAgentInstance(
        SELF_TEST_AGENT_ID,
        { "prompts.system": firstMarker },
        signal,
        scope.token,
      );
      if (!id) throw new SkipStep(`template '${SELF_TEST_AGENT_ID}' is not available on this deployment`);
      return { value: id, detail: id };
    });
    const need = (): string => {
      if (!agentId) throw new SkipStep("agent instance missing");
      return agentId;
    };

    await runStep(report, "query-system-prompt", "The system prompt set at enrollment is delivered", async () => {
      const { answer } = await turn(need());
      if (!answer.includes(firstMarker)) throw new Error(`'${firstMarker}' not delivered (${answer.slice(-100)})`);
      return { value: undefined, detail: "system prompt echoed back" };
    });
    await runStep(report, "effective-model", "The agent's chat model resolves and is usable", async () => {
      const model = await deps.effectiveModel(need());
      if (!model.name) throw new Error("no chat model resolves for this agent");
      if (!model.usable) throw new Error(`${model.name} is not enabled for this space; a turn would fail`);
      return { value: undefined, detail: model.name };
    });
    await runStep(
      report,
      "tuning-update",
      `An updated system prompt reaches each of ${REPEATED_TURNS} following turns`,
      async () => {
        const id = need();
        await deps.updateAgent(id, { system: secondMarker });
        currentMarker = secondMarker;
        for (let i = 1; i <= REPEATED_TURNS; i++) {
          const { answer } = await turn(id);
          if (!answer.includes(secondMarker) || answer.includes(firstMarker)) {
            throw new Error(`turn ${i} still runs on the previous configuration`);
          }
        }
        return { value: undefined, detail: `${REPEATED_TURNS} turns on the new configuration` };
      },
    );
    await runStep(report, "disabled-agent", "A disabled agent cannot run, and runs again once enabled", async () => {
      const id = need();
      await deps.updateAgent(id, { enabled: false });
      // The control plane refuses a disabled instance with 409 before any
      // execution; any other failure says nothing about the disable.
      let refusal: unknown = null;
      try {
        await turn(id);
      } catch (error) {
        refusal = error;
      } finally {
        await deps.updateAgent(id, { enabled: true });
      }
      if (refusal === null) throw new Error("a disabled agent answered a turn");
      if (statusOf(refusal) !== 409) throw new Error(`the disabled agent failed otherwise: ${describeError(refusal)}`);
      const { answer } = await turn(id);
      if (!answer.includes(currentMarker)) throw new Error("the re-enabled agent did not answer");
      return { value: undefined, detail: "refused while disabled, answered once enabled" };
    });

    await runStep(report, "copy-targets", "Copy targets include your personal space", async () => {
      const targets = await deps.copyTargets(need());
      const personal = targets.find((t) => t.teamId === deps.teamId);
      if (!personal) throw new Error("the personal space is not offered as a copy target");
      if (!personal.templateEnabled) throw new Error("the template is not enabled for the personal space");
      return { value: undefined, detail: `${targets.length} target(s)` };
    });
    await runStep(report, "duplicate", "A duplicate under a chosen name keeps the configuration", async () => {
      const result = await deps.duplicate(need(), duplicateName);
      if (!result.agentId) throw new Error(`the duplicate was refused (${result.errorCode ?? "no reason"})`);
      copies.push(result.agentId);
      if (result.name !== duplicateName) throw new Error(`the duplicate is named '${result.name}'`);
      nameTaken = true;
      const listed = (await deps.listAgents()).some((a) => a.id === result.agentId && a.name === duplicateName);
      if (!listed) throw new Error("the duplicate is not listed");
      const { answer } = await turn(result.agentId);
      if (!answer.includes(currentMarker)) throw new Error("the duplicate lost the system prompt");
      return { value: undefined, detail: result.agentId };
    });
    await runStep(report, "duplicate-conflict", "A second duplicate under the same name is refused", async () => {
      const id = need();
      if (!nameTaken) throw new SkipStep("no duplicate holds the name yet");
      const outcome = await deps.duplicate(id, duplicateName);
      if (outcome.agentId) {
        copies.push(outcome.agentId);
        throw new Error("a second agent was created under a taken name");
      }
      if (outcome.errorCode !== "agent_name_conflict")
        throw new Error(`the copy failed for another reason (${outcome.errorCode ?? "no conflict code"})`);
      return { value: undefined, detail: outcome.errorCode };
    });
    await runStep(report, "copy-free-name", "A copy without a name gets a free one", async () => {
      const result = await deps.duplicate(need());
      if (!result.agentId) throw new Error(`the copy was refused (${result.errorCode ?? "no reason"})`);
      copies.push(result.agentId);
      const names = (await deps.listAgents()).filter((a) => a.id === agentId || a.id === result.agentId);
      if (new Set(names.map((a) => a.name)).size !== 2) throw new Error("the copy reuses the source's name");
      return { value: undefined, detail: result.name ?? result.agentId };
    });

    await runStep(
      report,
      "concurrent-turns",
      `${CONCURRENT_SESSIONS} concurrent turns each receive only their own context`,
      async () => {
        const id = need();
        const markers = Array.from({ length: CONCURRENT_SESSIONS }, (_, i) =>
          scope.name(`${CONTEXT_PROMPT_MARKER_BASE}${i}`),
        );
        const mine: string[] = [];
        for (const [i, marker] of markers.entries()) {
          const promptId = await deps.createContextPrompt(scope.name(`fred-selftest-concurrent-${i}`), marker);
          prompts.push(promptId);
          const sessionId = await deps.createSession(id, scope.token);
          sessions.push(sessionId);
          await deps.attachSessionPrompts(sessionId, [promptId]);
          mine.push(sessionId);
        }
        const answers = await Promise.all(mine.map((sessionId) => turn(id, sessionId)));
        answers.forEach(({ answer }, i) => {
          if (!answer.includes(markers[i])) throw new Error(`session ${mine[i]} did not receive its own context`);
          const crossed = markers.findIndex((m, j) => j !== i && answer.includes(m));
          if (crossed !== -1) throw new Error(`session ${mine[i]} received the context of session ${mine[crossed]}`);
        });
        return { value: undefined, detail: `${CONCURRENT_SESSIONS} isolated answers` };
      },
    );
  } finally {
    for (const [i, id] of sessions.entries())
      await cleanup(report, `delete-session-${i}`, "Delete a test session", id, deps.deleteSession);
    for (const [i, id] of prompts.entries())
      await cleanup(report, `delete-prompt-${i}`, "Delete a test prompt", id, deps.deleteContextPrompt);
    for (const [i, id] of copies.entries())
      await cleanup(report, `delete-copy-${i}`, "Delete an agent copy", id, deps.deleteAgentInstance);
    await cleanup(report, "delete-agent", "Delete the self-test agent", agentId, deps.deleteAgentInstance);
    await runStep(
      report,
      "verify-agents-deleted",
      "Verify the test agents are gone",
      async () => {
        const created = [agentId, ...copies].filter((id): id is string => id != null);
        if (created.length === 0) throw new SkipStep("nothing was created");
        const left = (await deps.listAgents()).filter((a) => created.includes(a.id));
        if (left.length) throw new Error(`${left.length} test agent(s) still listed`);
        return { value: undefined, detail: `${created.length} agent(s) removed` };
      },
      { optional: true },
    );
  }
};
