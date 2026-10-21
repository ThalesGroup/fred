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
import type { PipelineDeps, Scenario } from "../types";
import { CONTEXT_PROMPT_MARKER_BASE, PROMPT_PROBE, SELF_TEST_AGENT_ID } from "./corpus";
import { cleanup, expectRefused, newRunScope } from "./runScope";

export interface PromptsDeps extends PipelineDeps {
  createPrompt: (args: { name: string; text: string; categoryId?: string; command?: string }) => Promise<string>;
  updatePrompt: (
    id: string,
    args: { name: string; text: string; categoryId?: string; command?: string },
  ) => Promise<void>;
  readPrompt: (id: string) => Promise<{ text: string; categoryId: string | null; favorite: boolean }>;
  setFavorite: (id: string, favorite: boolean) => Promise<void>;
  listFavorites: () => Promise<string[]>;
  listCommands: () => Promise<Array<{ promptId: string; command: string }>>;
  createCategory: (name: string) => Promise<string>;
  renameCategory: (id: string, name: string) => Promise<void>;
  listCategories: () => Promise<Array<{ id: string; name: string }>>;
  deleteCategory: (id: string) => Promise<void>;
  marketplaceCount: () => Promise<number>;
}

/** Prompts family, in the personal space: the agent echoes the context prompt it receives. */
export const promptsScenario: Scenario<PromptsDeps> = async (deps, report, signal) => {
  const scope = newRunScope();
  const firstMarker = scope.name(`${CONTEXT_PROMPT_MARKER_BASE}A`);
  const secondMarker = scope.name(`${CONTEXT_PROMPT_MARKER_BASE}B`);
  const promptName = scope.name("fred-selftest-prompt");
  const command = `selftest-${scope.token.toLowerCase()}`;
  let agentId: string | null = null;
  let categoryId: string | null = null;
  let promptId: string | null = null;
  let sessionId: string | null = null;

  const askForPrompts = () => {
    if (!agentId || !sessionId) throw new SkipStep("agent instance or session missing");
    return deps.runAgentTurn({ agentInstanceId: agentId, question: PROMPT_PROBE, libraryIds: [], sessionId, signal });
  };

  try {
    agentId = await runStep(report, "provision-agent", "Provision the self-test agent", async () => {
      const id = await deps.provisionAgentInstance(SELF_TEST_AGENT_ID, undefined, signal, scope.token);
      if (!id) throw new SkipStep(`template '${SELF_TEST_AGENT_ID}' is not available on this deployment`);
      return { value: id, detail: id };
    });
    await runStep(report, "create-category", "Create a prompt category", async () => {
      const id = await deps.createCategory(scope.name("Self-test category"));
      categoryId = id;
      if (!(await deps.listCategories()).some((c) => c.id === id)) throw new Error("the new category is not listed");
      return { value: id, detail: id };
    });
    await runStep(report, "create-prompt", "Create a personal prompt with a category and a command", async () => {
      const id = await deps.createPrompt({
        name: promptName,
        text: `Self-test context prompt. Delivery marker: ${firstMarker}`,
        categoryId: categoryId ?? undefined,
        command,
      });
      promptId = id;
      const stored = await deps.readPrompt(id);
      if (categoryId && stored.categoryId !== categoryId) throw new Error("the prompt lost its category");
      return { value: id, detail: id };
    });
    sessionId = await runStep(report, "create-session", "Create a chat session", async () => {
      if (!agentId) throw new SkipStep("agent instance missing");
      const id = await deps.createSession(agentId, scope.token);
      return { value: id, detail: id };
    });
    await runStep(report, "attach-prompt", "Attach the prompt to the session", async () => {
      if (!sessionId || !promptId) throw new SkipStep("session or prompt missing");
      await deps.attachSessionPrompts(sessionId, [promptId]);
      return { value: undefined, detail: `prompt ${promptId} attached to session ${sessionId}` };
    });
    await runStep(report, "query-context-prompt", "The attached prompt is delivered to the agent", async () => {
      const { answer } = await askForPrompts();
      if (!answer.includes(firstMarker)) throw new Error(`'${firstMarker}' not delivered (${answer.slice(-120)})`);
      return { value: undefined, detail: "context prompt echoed back" };
    });
    await runStep(report, "prompt-update", "An edited prompt is delivered with its new text", async () => {
      if (!promptId) throw new SkipStep("prompt missing");
      await deps.updatePrompt(promptId, {
        name: promptName,
        text: `Self-test context prompt. Delivery marker: ${secondMarker}`,
        categoryId: categoryId ?? undefined,
        command,
      });
      const { answer } = await askForPrompts();
      if (!answer.includes(secondMarker) || answer.includes(firstMarker)) {
        throw new Error("the session still receives the previous prompt text");
      }
      return { value: undefined, detail: "new text echoed back" };
    });
    await runStep(report, "prompt-command", "The prompt's command is offered", async () => {
      if (!promptId) throw new SkipStep("prompt missing");
      const offered = (await deps.listCommands()).some((c) => c.promptId === promptId && c.command === command);
      if (!offered) throw new Error(`command '${command}' is not offered`);
      return { value: undefined, detail: command };
    });
    await runStep(report, "favorite", "A prompt can be marked and unmarked as favorite", async () => {
      if (!promptId) throw new SkipStep("prompt missing");
      await deps.setFavorite(promptId, true);
      if (!(await deps.listFavorites()).includes(promptId)) throw new Error("the prompt is not listed as favorite");
      await deps.setFavorite(promptId, false);
      if ((await deps.listFavorites()).includes(promptId)) throw new Error("the favorite mark could not be removed");
      return { value: undefined, detail: "marked, then unmarked" };
    });
    await runStep(report, "rename-category", "A category can be renamed", async () => {
      if (!categoryId) throw new SkipStep("category missing");
      const name = scope.name("Self-test category renamed");
      await deps.renameCategory(categoryId, name);
      if (!(await deps.listCategories()).some((c) => c.id === categoryId && c.name === name)) {
        throw new Error("the category kept its old name");
      }
      return { value: undefined, detail: name };
    });
    await runStep(report, "marketplace", "The prompt marketplace can be read", async () => ({
      value: undefined,
      detail: `${await deps.marketplaceCount()} published prompt(s)`,
    }));
  } finally {
    await cleanup(report, "delete-session", "Delete the chat session", sessionId, deps.deleteSession);
    await cleanup(report, "delete-prompt", "Delete the prompt", promptId, deps.deleteContextPrompt);
    await cleanup(report, "delete-category", "Delete the category", categoryId, deps.deleteCategory);
    await cleanup(report, "delete-agent", "Delete the self-test agent", agentId, deps.deleteAgentInstance);
    await runStep(
      report,
      "prompt-gone",
      "A deleted prompt can no longer be read",
      async () => {
        if (!promptId) throw new SkipStep("no prompt was created");
        const id = promptId;
        const status = await expectRefused(() => deps.readPrompt(id), "reading the deleted prompt", [404]);
        if (categoryId && (await deps.listCategories()).some((c) => c.id === categoryId)) {
          throw new Error("the deleted category is still listed");
        }
        return { value: undefined, detail: `HTTP ${status}` };
      },
      { optional: true },
    );
  }
};
