// @vitest-environment happy-dom
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

// Coverage for the staged Save/Cancel model: Créer/Éditer/Supprimer only
// build a local draft — the backend must see exactly the create/rename/delete
// set the user actually decided, and only once "Enregistrer" is clicked.
// "Annuler" must call none of the three mutations.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}::${JSON.stringify(opts)}` : key),
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: () => {} }),
}));

const calls = {
  create: [] as { teamId: string; createPromptCategoryRequest: { name: string } }[],
  update: [] as { teamId: string; categoryId: string; updatePromptCategoryRequest: { name: string } }[],
  delete: [] as { teamId: string; categoryId: string }[],
};

vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  usePostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostMutation: () => [
    (args: (typeof calls.create)[number]) => {
      calls.create.push(args);
      return {
        unwrap: async () => ({ id: "new-id", team_id: args.teamId, name: args.createPromptCategoryRequest.name }),
      };
    },
    { isLoading: false },
  ],
  usePutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutMutation: () => [
    (args: (typeof calls.update)[number]) => {
      calls.update.push(args);
      return {
        unwrap: async () => ({
          id: args.categoryId,
          team_id: args.teamId,
          name: args.updatePromptCategoryRequest.name,
        }),
      };
    },
    { isLoading: false },
  ],
  useDeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteMutation: () => [
    (args: (typeof calls.delete)[number]) => {
      calls.delete.push(args);
      return { unwrap: async () => undefined };
    },
  ],
}));

import ManageCategoriesDialog from "./ManageCategoriesDialog";

const CATEGORIES = [
  { id: "cat-1", team_id: "team-1", name: "Analyse" },
  { id: "cat-2", team_id: "team-1", name: "Communication" },
];

function flush() {
  return act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("ManageCategoriesDialog", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    calls.create = [];
    calls.update = [];
    calls.delete = [];
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("Save applies exactly the rename + create + delete the user staged, nothing more", async () => {
    const onChanged = vi.fn();
    const onClose = vi.fn();

    act(() => {
      root.render(
        <ManageCategoriesDialog
          open
          teamId="team-1"
          categories={CATEGORIES}
          usedCategoryIds={new Set()}
          onClose={onClose}
          onChanged={onChanged}
        />,
      );
    });

    const dialog = document.body;

    // Rename "Analyse" -> "Analyse et synthèse".
    const editAnalyse = dialog.querySelector(
      '[aria-label*="editAria"][aria-label*="Analyse"]:not([aria-label*="Communication"])',
    ) as HTMLButtonElement;
    expect(editAnalyse).toBeTruthy();
    act(() => {
      editAnalyse.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    const editInput = dialog.querySelector("li input") as HTMLInputElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(editInput, "Analyse et synthèse");
      editInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const commitButton = dialog.querySelector(
      '[aria-label="rework.promptCategories.manage.saveAria"]',
    ) as HTMLButtonElement;
    act(() => {
      commitButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    // Delete "Communication".
    const deleteCommunication = dialog.querySelector(
      '[aria-label*="deleteAria"][aria-label*="Communication"]',
    ) as HTMLButtonElement;
    expect(deleteCommunication).toBeTruthy();
    act(() => {
      deleteCommunication.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    // Create "Support client".
    const createInput = dialog.querySelector(".createRow input, [class*='createRow'] input") as HTMLInputElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(createInput, "Support client");
      createInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const createButton = Array.from(dialog.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.promptCategories.manage.create",
    ) as HTMLButtonElement;
    expect(createButton).toBeTruthy();
    act(() => {
      createButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    // Nothing hit the backend yet — everything so far is purely local draft state.
    expect(calls.create).toHaveLength(0);
    expect(calls.update).toHaveLength(0);
    expect(calls.delete).toHaveLength(0);

    // Now commit via Enregistrer.
    const saveButton = Array.from(dialog.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.save",
    ) as HTMLButtonElement;
    expect(saveButton).toBeTruthy();
    act(() => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();

    expect(calls.update).toEqual([
      { teamId: "team-1", categoryId: "cat-1", updatePromptCategoryRequest: { name: "Analyse et synthèse" } },
    ]);
    expect(calls.delete).toEqual([{ teamId: "team-1", categoryId: "cat-2" }]);
    expect(calls.create).toEqual([{ teamId: "team-1", createPromptCategoryRequest: { name: "Support client" } }]);
    expect(onChanged).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("Annuler discards every staged change and calls no mutation", () => {
    const onChanged = vi.fn();
    const onClose = vi.fn();

    act(() => {
      root.render(
        <ManageCategoriesDialog
          open
          teamId="team-1"
          categories={CATEGORIES}
          usedCategoryIds={new Set()}
          onClose={onClose}
          onChanged={onChanged}
        />,
      );
    });

    const dialog = document.body;

    // Delete "Communication" (staged only).
    const deleteCommunication = dialog.querySelector(
      '[aria-label*="deleteAria"][aria-label*="Communication"]',
    ) as HTMLButtonElement;
    act(() => {
      deleteCommunication.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    const cancelButton = Array.from(dialog.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.cancel",
    ) as HTMLButtonElement;
    expect(cancelButton).toBeTruthy();
    act(() => {
      cancelButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(calls.create).toHaveLength(0);
    expect(calls.update).toHaveLength(0);
    expect(calls.delete).toHaveLength(0);
    expect(onChanged).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("disables delete with an explanatory tooltip for a category that has prompts attached", () => {
    act(() => {
      root.render(
        <ManageCategoriesDialog
          open
          teamId="team-1"
          categories={CATEGORIES}
          usedCategoryIds={new Set(["cat-2"])}
          onClose={vi.fn()}
          onChanged={vi.fn()}
        />,
      );
    });

    const dialog = document.body;

    const deleteCommunication = dialog.querySelector(
      '[aria-label*="deleteAria"][aria-label*="Communication"]',
    ) as HTMLButtonElement;
    expect(deleteCommunication.disabled).toBe(true);
    // Tooltip content only exists (portaled onto body) while the trigger is
    // hovered — enter the wrapper before asserting on it.
    const wrapper = deleteCommunication.closest('[class*="tooltip-wrapper"]') as HTMLElement;
    act(() => {
      wrapper.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    const blockedTooltip = document.body.querySelector('[role="tooltip"]');
    expect(blockedTooltip?.textContent).toBe("rework.promptCategories.manage.deleteBlocked");
    act(() => {
      wrapper.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
    });

    // "Analyse" has no prompts attached — delete stays enabled with the
    // normal per-category tooltip.
    const deleteAnalyse = dialog.querySelector(
      '[aria-label*="deleteAria"][aria-label*="Analyse"]:not([aria-label*="Communication"])',
    ) as HTMLButtonElement;
    expect(deleteAnalyse.disabled).toBe(false);
  });
});
