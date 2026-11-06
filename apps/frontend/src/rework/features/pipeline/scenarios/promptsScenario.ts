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

import type {
  CreatePromptApiArg,
  UpdatePromptApiArg,
  GetPromptApiArg,
  DeletePromptApiArg,
  CreatePromptCategoryApiArg,
  RenamePromptCategoryApiArg,
  DeletePromptCategoryApiArg,
  Prompt,
  PromptSummary,
  PromptCategory,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import { cleanup, expectRefused, newRunScope } from "./runScope";

export interface PromptsDeps {
  resolveSpaceId: () => Promise<string>;
  createPrompt: (args: CreatePromptApiArg) => Promise<Prompt>;
  updatePrompt: (args: UpdatePromptApiArg) => Promise<Prompt>;
  readPrompt: (args: GetPromptApiArg) => Promise<Prompt>;
  deletePrompt: (args: DeletePromptApiArg) => Promise<void>;
  listPrompts: (spaceId: string) => Promise<PromptSummary[]>;
  setFavorite: (spaceId: string, promptId: string, favorite: boolean) => Promise<void>;
  createCategory: (args: CreatePromptCategoryApiArg) => Promise<PromptCategory>;
  renameCategory: (args: RenamePromptCategoryApiArg) => Promise<PromptCategory>;
  listCategories: (spaceId: string) => Promise<PromptCategory[]>;
  deleteCategory: (args: DeletePromptCategoryApiArg) => Promise<void>;
  marketplaceCount?: (spaceId: string) => Promise<number>;
}

/** Validate the library consumed by the composer, without the retired session-context attachment path. */
export const promptsScenario: Scenario<PromptsDeps> = async (deps, report, signal) => {
  const scope = newRunScope();
  const logicalName = `selftest-${scope.token.toLowerCase()}`;
  const displayName = scope.name("Self-test prompt");
  const text = `  Self-test prompt ${scope.token}\nPreserve whitespace.  `;
  const description = scope.name("Self-test description");
  const spaceId = await runStep(report, "prompt-space", "Resolve the Weaver prompt space", async () => {
    signal.throwIfAborted();
    const id = await deps.resolveSpaceId();
    return { value: id, detail: id };
  });
  if (!spaceId) return;
  let categoryId: string | null = null;
  let promptId: string | null = null;

  try {
    await runStep(report, "create-category", "Create a prompt category", async () => {
      signal.throwIfAborted();
      const created = await deps.createCategory({
        spaceId,
        promptCategoryRequest: { name: scope.name("Self-test category") },
      });
      categoryId = created.id;
      if (
        created.space_id !== spaceId ||
        !(await deps.listCategories(spaceId)).some((c) => c.id === created.id && c.space_id === spaceId)
      )
        throw new Error("the new category is not listed in the scenario space");
      return { value: created.id, detail: created.id };
    });
    await runStep(report, "create-prompt", "Create a prompt with a stable identity, category and command", async () => {
      signal.throwIfAborted();
      if (!categoryId) throw new SkipStep("category missing");
      const created = await deps.createPrompt({
        spaceId,
        createPromptRequest: {
          logical_name: logicalName,
          display_name: displayName,
          text,
          description,
          tags: [scope.token],
          category_id: categoryId,
        },
      });
      promptId = created.prompt_id;
      const stored = await deps.readPrompt({ spaceId, promptId });
      if (
        stored.prompt_id !== promptId ||
        stored.space_id !== spaceId ||
        stored.logical_name !== logicalName ||
        stored.display_name !== displayName ||
        stored.text !== text ||
        stored.category_id !== categoryId
      )
        throw new Error("the stored prompt differs from the created definition or space");
      return { value: promptId, detail: promptId };
    });
    await runStep(report, "category-in-use", "Refuse deletion of an assigned category", async () => {
      signal.throwIfAborted();
      if (!categoryId || !promptId) throw new SkipStep("category or prompt missing");
      const id = categoryId;
      const status = await expectRefused(
        () => deps.deleteCategory({ spaceId, categoryId: id }),
        "deleting an assigned category",
        [409],
      );
      return { value: undefined, detail: `HTTP ${status}` };
    });
    await runStep(
      report,
      "prompt-update",
      "Edit title and text while preserving omitted fields and command",
      async () => {
        signal.throwIfAborted();
        if (!promptId) throw new SkipStep("prompt missing");
        const editedName = `${displayName} edited`;
        const editedText = `${text}\nEdited ${scope.token}`;
        await deps.updatePrompt({
          spaceId,
          promptId,
          updatePromptRequest: { display_name: editedName, text: editedText },
        });
        const stored = await deps.readPrompt({ spaceId, promptId });
        if (
          stored.prompt_id !== promptId ||
          stored.space_id !== spaceId ||
          stored.logical_name !== logicalName ||
          stored.display_name !== editedName ||
          stored.text !== editedText ||
          stored.category_id !== categoryId ||
          stored.description !== description ||
          stored.tags.join() !== scope.token
        )
          throw new Error("the partial update changed identity, lost omitted fields or retained old text");
        return { value: undefined, detail: "updated title and full text; identity and omitted fields preserved" };
      },
    );
    await runStep(report, "prompt-command", "The prompt catalog preserves the slash-command identity", async () => {
      signal.throwIfAborted();
      if (!promptId) throw new SkipStep("prompt missing");
      const offered = (await deps.listPrompts(spaceId)).some(
        (prompt) => prompt.prompt_id === promptId && prompt.space_id === spaceId && prompt.logical_name === logicalName,
      );
      if (!offered) throw new Error(`command '/${logicalName}' is not offered`);
      return { value: undefined, detail: `/${logicalName}` };
    });
    await runStep(report, "favorite", "The caller can mark and unmark a favorite", async () => {
      signal.throwIfAborted();
      if (!promptId) throw new SkipStep("prompt missing");
      for (const favorite of [true, false]) {
        await deps.setFavorite(spaceId, promptId, favorite);
        const listed = (await deps.listPrompts(spaceId)).find((prompt) => prompt.prompt_id === promptId);
        if (listed?.is_favorite !== favorite || (await deps.readPrompt({ spaceId, promptId })).is_favorite !== favorite)
          throw new Error("the caller's favorite state differs between the detail and catalog");
      }
      return { value: undefined, detail: "marked, then unmarked" };
    });
    await runStep(report, "rename-category", "A category can be renamed within its space", async () => {
      signal.throwIfAborted();
      if (!categoryId) throw new SkipStep("category missing");
      const name = scope.name("Self-test category renamed");
      await deps.renameCategory({ spaceId, categoryId, promptCategoryRequest: { name } });
      if (
        !(await deps.listCategories(spaceId)).some(
          (c) => c.id === categoryId && c.space_id === spaceId && c.name === name,
        )
      )
        throw new Error("the category kept its old name or moved space");
      return { value: undefined, detail: name };
    });
    const marketplaceCount = deps.marketplaceCount;
    if (marketplaceCount)
      await runStep(report, "marketplace", "The prompt marketplace can be read", async () => {
        signal.throwIfAborted();
        return { value: undefined, detail: `${await marketplaceCount(spaceId)} published prompt(s)` };
      });
  } finally {
    await cleanup(
      report,
      "delete-prompt",
      "Delete the prompt",
      promptId,
      (id) => deps.deletePrompt({ spaceId, promptId: id }),
      async (id) => {
        await expectRefused(() => deps.readPrompt({ spaceId, promptId: id }), "reading the deleted prompt", [404]);
        if ((await deps.listPrompts(spaceId)).some((prompt) => prompt.prompt_id === id))
          throw new Error("Deleted prompt remains in its catalog.");
      },
    );
    await cleanup(
      report,
      "delete-category",
      "Delete the category",
      categoryId,
      (id) => deps.deleteCategory({ spaceId, categoryId: id }),
      async (id) => {
        if ((await deps.listCategories(spaceId)).some((category) => category.id === id))
          throw new Error(`category ${id} is still listed after deletion`);
      },
    );
  }
};
