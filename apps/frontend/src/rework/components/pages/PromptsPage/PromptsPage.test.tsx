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

// Regression coverage for issue #1996 (Prompts): "click a card to edit it,
// press Esc, click again — the form is empty". Confirmed mechanism: RTK
// Query's `data` field (as opposed to `currentData`) keeps returning the
// last successful result for a query — the SAME object reference — even
// while the query is skipped, and again once unskipped for the same cache
// key (see @reduxjs/toolkit's buildHooks.ts `queryStatePreSelector`, which
// falls back to `lastResult.data` whenever the live state is uninitialized,
// and only clears `lastResult` when unskipped args differ from the last
// ones). So `useEffect(() => { if (editDetail) ... }, [editDetail])` never
// re-fires on reopen: `editDetail` never changed reference to begin with.
// The mock query hook below reproduces that exact persistence so this test
// fails against the un-fixed component and passes once PromptsPage tracks
// "which id the form is currently seeded for" instead of trusting object
// identity.

import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({ teamId: "team-1", selectedTeam: undefined }),
}));
// Card click now opens a read-only view dialog (PROMPT-09 follow-up); editing
// is only reachable through the card's hover-edit pencil, which is gated on
// `canManage` — force it on so the edit-form-reseed regression tests below
// can still reach that pencil.
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: () => {} }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: () => {}, showSuccess: () => {} }),
}));

const PROMPT_SUMMARY = {
  id: "prompt-1",
  name: "Real Name",
  description: "Real description",
  category_id: null,
};

// Stable object reference on purpose: the real backend response for the
// same promptId/teamId is exactly this reused, not a fresh object per call.
const PROMPT_DETAIL = {
  id: "prompt-1",
  team_id: "team-1",
  name: "Real Name",
  description: "Real description",
  category_id: null,
  tags: ["greeting"],
  text: "Real prompt text",
};

// A second prompt used only by the cross-prompt-leak test below. Its detail
// query "resolves" only once `promptBReady` is flipped, letting the test
// hold it in the uninitialized/loading gap where a naive re-seed guard would
// leak the previous prompt's still-lingering `data` into its form.
const PROMPT_B_SUMMARY = {
  id: "prompt-2",
  name: "Other Name",
  description: "Other description",
  category_id: null,
};
const PROMPT_B_DETAIL = {
  id: "prompt-2",
  team_id: "team-1",
  name: "Other Name",
  description: "Other description",
  category_id: null,
  tags: [],
  text: "Other prompt text",
};
let promptBReady = false;

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery: () => ({
    data: [PROMPT_SUMMARY, PROMPT_B_SUMMARY],
    isLoading: false,
    isFetching: false,
    isUninitialized: false,
    isError: false,
    refetch: async () => {},
  }),
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery: () => ({
    data: [],
    refetch: async () => {},
  }),
  // Faithful reproduction of RTK Query's confirmed `data` persistence
  // (verified directly against @reduxjs/toolkit's buildHooks.ts
  // `queryStatePreSelector`: `lastValue` is a per-hook-instance ref that is
  // NEVER cleared on an args change, only on a very specific same-args store
  // reset). So switching from one promptId to a different one keeps
  // returning the PREVIOUS id's data for as long as the new id's fetch
  // hasn't resolved yet — `lastData` below models exactly that.
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: (
    args: { promptId: string },
    opts: { skip: boolean },
  ) => {
    const lastData = useRef<typeof PROMPT_DETAIL | undefined>(undefined);
    if (!opts.skip) {
      if (args.promptId === PROMPT_DETAIL.id) {
        lastData.current = PROMPT_DETAIL;
      } else if (args.promptId === PROMPT_B_DETAIL.id && promptBReady) {
        lastData.current = PROMPT_B_DETAIL;
      }
      // else: prompt-2 requested but not "resolved" yet — lastData.current
      // is deliberately left untouched, lingering on whatever it held
      // before (prompt-1's detail, if that was open last).
    }
    return { data: lastData.current };
  },
  usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation: () => [
    async () => ({ unwrap: async () => undefined }),
    { isLoading: false },
  ],
  usePutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutMutation: () => [
    async () => ({ unwrap: async () => undefined }),
    { isLoading: false },
  ],
  useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation: () => [
    async () => ({ unwrap: async () => undefined }),
  ],
  usePostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostMutation: () => [
    async () => ({ unwrap: async () => undefined }),
  ],
  usePostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostMutation: () => [
    async () => ({ unwrap: async () => undefined }),
  ],
  usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation: () => [
    async () => ({ unwrap: async () => undefined }),
  ],
  usePostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostMutation: () => [
    async () => ({ unwrap: async () => undefined }),
    { isLoading: false },
  ],
  usePutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutMutation: () => [
    async () => ({ unwrap: async () => undefined }),
    { isLoading: false },
  ],
  useDeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteMutation: () => [
    async () => ({ unwrap: async () => undefined }),
  ],
}));

import PromptsPage from "./PromptsPage";

// FullPageModal renders through a `createPortal` into a div appended
// directly to `document.body` (see Portal.tsx) — it is NOT a descendant of
// the `container` the page itself is mounted into, so form fields must be
// queried from the dialog, not from `container`.
function formValues() {
  const dialog = document.querySelector('[role="dialog"]') as HTMLElement | null;
  if (!dialog) return { name: "", description: "", text: "" };
  const inputs = dialog.querySelectorAll("input");
  const textarea = dialog.querySelector("textarea");
  return {
    name: (inputs[0] as HTMLInputElement | undefined)?.value ?? "",
    description: (inputs[1] as HTMLInputElement | undefined)?.value ?? "",
    text: (textarea as HTMLTextAreaElement | null)?.value ?? "",
  };
}

describe("PromptsPage edit form reseed", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("re-populates the form when the same card is reopened after closing via Escape", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root.render(<PromptsPage />);
    });

    // Card click now opens the read-only view dialog — reach the edit form
    // through the card's more-menu → "Edit" item instead (the pencil became a
    // more-menu with the prompts marketplace, PROMPT-06). The menu renders in a
    // portal on document.body, so the Edit item is queried from the document.
    const openEditForm = (index = 0) => {
      const cards = container.querySelectorAll('[role="button"]');
      const card = cards[index] as HTMLElement;
      const moreButton = Array.from(card.querySelectorAll("button")).find((b) => b.textContent?.includes("more_vert"));
      act(() => {
        moreButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      });
      const editItem = Array.from(document.querySelectorAll("li")).find((el) =>
        el.textContent?.includes("card.menu.edit"),
      );
      act(() => {
        editItem?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      });
    };

    // First open: form should be fully seeded from the detail query.
    openEditForm();
    expect(formValues()).toEqual({
      name: "Real Name",
      description: "Real description",
      text: "Real prompt text",
    });

    // Close via Escape, exactly like the reported repro.
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(document.querySelector('[role="dialog"]')).toBeNull();

    // Reopen the SAME card: the form must be fully seeded again, not left
    // at openPrompt()'s partial pre-fill (empty name/description/text).
    openEditForm();
    expect(formValues()).toEqual({
      name: "Real Name",
      description: "Real description",
      text: "Real prompt text",
    });
  });

  it("does not leak the previous prompt's data into a different prompt opened before its query resolves", () => {
    // PR review (chatgpt-codex-connector): closing prompt 1 and opening
    // prompt 2 before prompt 2's detail query resolves must not seed
    // prompt 2's form with prompt 1's still-lingering `editDetail`.
    promptBReady = false;

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root.render(<PromptsPage />);
    });

    const openEditForm = (index: number) => {
      const cards = container.querySelectorAll('[role="button"]');
      const card = cards[index] as HTMLElement;
      const moreButton = Array.from(card.querySelectorAll("button")).find((b) => b.textContent?.includes("more_vert"));
      act(() => {
        moreButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      });
      const editItem = Array.from(document.querySelectorAll("li")).find((el) =>
        el.textContent?.includes("card.menu.edit"),
      );
      act(() => {
        editItem?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      });
    };

    // Open prompt 1 — resolves immediately, seeds the form.
    openEditForm(0);
    expect(formValues()).toEqual({
      name: "Real Name",
      description: "Real description",
      text: "Real prompt text",
    });

    // Close, then open prompt 2 while its detail query is still pending
    // (promptBReady is false — mirrors the real gap before a fresh fetch
    // resolves). The form must NOT show prompt 1's leftover content.
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    openEditForm(1);
    expect(formValues()).toEqual({ name: "", description: "", text: "" });

    // Prompt 2's query resolves: the form must now show ITS data.
    promptBReady = true;
    act(() => {
      root.render(<PromptsPage />);
    });
    expect(formValues()).toEqual({
      name: "Other Name",
      description: "Other description",
      text: "Other prompt text",
    });
  });
});

describe("PromptsPage card click", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("opens a read-only view dialog instead of the edit form", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root.render(<PromptsPage />);
    });

    const card = container.querySelectorAll('[role="button"]')[0] as HTMLElement;
    act(() => {
      card.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    const dialog = document.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog).toBeTruthy();
    // No editable inputs/textareas at all — this is a pure display view, not
    // the edit form (the prompt text itself is a non-interactive scrollable
    // div, not a textarea).
    expect(dialog.querySelectorAll("input, textarea")).toHaveLength(0);
    expect(dialog.textContent).toContain("Real prompt text");
  });

  it("does not show the previous prompt's data while the next prompt's detail query is pending", () => {
    // Same root cause as issue #1996 (see the edit-form regression tests
    // above), but for PromptViewDialog: RTK Query's `data` keeps returning
    // the previous promptId's result for a moment after switching ids.
    promptBReady = false;

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root.render(<PromptsPage />);
    });

    const clickCard = (index: number) => {
      const card = container.querySelectorAll('[role="button"]')[index] as HTMLElement;
      act(() => {
        card.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      });
    };

    // Open prompt 1 — resolves immediately.
    clickCard(0);
    let dialog = document.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog.textContent).toContain("Real prompt text");

    // Close, then open prompt 2 while its detail query is still pending. Must
    // show a loading state, never prompt 1's stale text.
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    clickCard(1);
    dialog = document.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog.querySelector('[role="status"]')).toBeTruthy();
    expect(dialog.textContent).not.toContain("Real prompt text");

    // Prompt 2's query resolves: the dialog must now show ITS data.
    promptBReady = true;
    act(() => {
      root.render(<PromptsPage />);
    });
    dialog = document.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog.textContent).toContain("Other prompt text");
  });
});
