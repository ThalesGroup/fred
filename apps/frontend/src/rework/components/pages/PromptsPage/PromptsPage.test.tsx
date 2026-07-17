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
vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "team-1" }),
}));
vi.mock("../../../../components/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: () => {} }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: () => {}, showSuccess: () => {} }),
}));

const PROMPT_SUMMARY = {
  id: "prompt-1",
  name: "Real Name",
  description: "Real description",
  category: "other" as const,
  is_default: false,
};

// Stable object reference on purpose: the real backend response for the
// same promptId/teamId is exactly this reused, not a fresh object per call.
const PROMPT_DETAIL = {
  id: "prompt-1",
  team_id: "team-1",
  name: "Real Name",
  description: "Real description",
  category: "other" as const,
  tags: ["greeting"],
  text: "Real prompt text",
};

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery: () => ({
    data: [PROMPT_SUMMARY],
    isLoading: false,
    isFetching: false,
    isUninitialized: false,
    isError: false,
    refetch: async () => {},
  }),
  // Faithful reproduction of RTK Query's confirmed `data` persistence:
  // returns the same PROMPT_DETAIL reference for a given id whenever not
  // skipped, and leaves it untouched (not reset to undefined) while skipped.
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: (
    args: { promptId: string },
    opts: { skip: boolean },
  ) => {
    const lastData = useRef<typeof PROMPT_DETAIL | undefined>(undefined);
    if (!opts.skip && args.promptId === PROMPT_DETAIL.id) {
      lastData.current = PROMPT_DETAIL;
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

    const openCard = () => {
      const card = container.querySelector('[role="button"]') as HTMLElement;
      act(() => {
        card.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      });
    };

    // First open: form should be fully seeded from the detail query.
    openCard();
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
    openCard();
    expect(formValues()).toEqual({
      name: "Real Name",
      description: "Real description",
      text: "Real prompt text",
    });
  });
});
