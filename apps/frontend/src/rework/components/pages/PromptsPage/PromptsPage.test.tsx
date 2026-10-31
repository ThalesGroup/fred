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

// Retains the edit/view reseed regressions while exercising the Weaver contract.
import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
import { SPACES, SPACE_A, SPACE_B } from "../TeamAgentsPage/weaverAgentFixtures";
import { promptFixture, promptSummaryFixture } from "./weaverPromptFixtures";
import type { Prompt, MySpace } from "../../../../slices/controlPlane/controlPlaneOpenApi";
const route = vi.hoisted(() => ({ teamId: "" }));
vi.mock("react-router-dom", () => ({ useParams: () => route }));
// The dialog itself is not rendered: the test reads what the page asked for
// and confirms by calling `onConfirm` directly.
type ConfirmationOptions = { title: string; message: string; confirmButtonLabel?: string; onConfirm: () => unknown };
const confirmation = vi.hoisted(() => ({ last: null as ConfirmationOptions | null }));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({
    showConfirmationDialog: (options: ConfirmationOptions) => {
      confirmation.last = options;
    },
  }),
}));
const toast = vi.hoisted(() => ({ showError: vi.fn(), showSuccess: vi.fn() }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => toast }));

const PROMPT_DETAIL = promptFixture();
const PROMPT_B_DETAIL = promptFixture({
  prompt_id: "prompt-2",
  display_name: "Other Name",
  logical_name: "other",
  description: "Other description",
  text: "Other prompt text",
});
let promptBReady = false;
let context: MySpace[] = SPACES;
let stamp = 1;
let catalogError = false;
const createCalls: unknown[] = [];
let createRejectsWith: unknown = null;
let deleteRejectsWith: unknown = null;
const authorize = vi.fn();
const update = vi.fn();
const remove = vi.fn();
const create = vi.fn();
const catalogRead = vi.fn();
const detailRead = vi.fn();
const copy = vi.hoisted(() => vi.fn());
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard: copy }));
vi.mock("../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi", () => ({
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => ({}),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: context, fulfilledTimeStamp: stamp, isError: false }),
  useAuthorizeSpaceMutation: () => [authorize],
  usePromptCatalogQuery: (args: unknown) => {
    catalogRead(args);
    return {
      currentData: {
        items: [promptSummaryFixture(PROMPT_DETAIL), promptSummaryFixture(PROMPT_B_DETAIL)],
        next_cursor: null,
      },
      isFetching: false,
      isError: catalogError,
      refetch: vi.fn(),
    };
  },
  useGetPromptQuery: (args: { promptId: string }, opts: { skip: boolean }) => {
    detailRead(args, opts);
    const lastData = useRef<Prompt | undefined>(undefined);
    const currentData = opts.skip
      ? undefined
      : args.promptId === PROMPT_DETAIL.prompt_id
        ? PROMPT_DETAIL
        : promptBReady
          ? PROMPT_B_DETAIL
          : undefined;
    if (currentData) lastData.current = currentData;
    return { data: lastData.current, currentData, isFetching: !opts.skip && !currentData, isError: false };
  },
  useCreatePromptMutation: () => [create, { isLoading: false }],
  useUpdatePromptMutation: () => [update, { isLoading: false }],
  useDeletePromptMutation: () => [remove, { isLoading: false }],
}));

import { EditorView } from "@codemirror/view";
import PromptsPage from "./PromptsPage";
import PromptViewDialog from "./PromptViewDialog/PromptViewDialog";

// FullPageModal renders through a `createPortal` into a div appended
// directly to `document.body` (see Portal.tsx) — it is NOT a descendant of
// the `container` the page itself is mounted into, so form fields must be
// queried from the dialog, not from `container`.
// Fields are read by their label rather than by position: the form has
// gained inputs before (the command), and an index-based reader silently
// starts asserting about the wrong box when that happens.
function fieldByLabel(label: string): HTMLInputElement | null {
  const dialog = document.querySelector('[role="dialog"]') as HTMLElement | null;
  if (!dialog) return null;
  for (const wrapper of Array.from(dialog.querySelectorAll("label"))) {
    if (wrapper.textContent?.includes(label)) {
      const input = wrapper.querySelector("input") ?? wrapper.parentElement?.querySelector("input");
      if (input) return input as HTMLInputElement;
    }
  }
  return null;
}

function formValues() {
  const dialog = document.querySelector('[role="dialog"]') as HTMLElement | null;
  if (!dialog) return { name: "", description: "", text: "" };
  // The prompt text is a CodeMirror document, not a form control: read it from
  // the editor's own state rather than off the DOM.
  const editor = dialog.querySelector(".cm-editor");
  return {
    name: fieldByLabel("form.name")?.value ?? "",
    description: fieldByLabel("form.description")?.value ?? "",
    text: editor ? (EditorView.findFromDOM(editor as HTMLElement)?.state.doc.toString() ?? "") : "",
  };
}

let container: HTMLDivElement;
let root: Root;
const render = () => act(() => root.render(<PromptsPage />));
const click = (element: Element | null | undefined) => {
  expect(element).toBeTruthy();
  act(() => element!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));
};
const button = (text: string) =>
  Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.trim().endsWith(text));
const escape = () => act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
function cardAction(action: string, index = 0) {
  const card = container.querySelectorAll('[role="button"]')[index];
  click(Array.from(card.querySelectorAll("button")).find((b) => b.textContent?.includes("more_vert")));
  click(Array.from(document.querySelectorAll("li")).find((el) => el.textContent?.includes(`card.menu.${action}`)));
}
function typeInto(input: HTMLInputElement, value: string) {
  expect(input).toBeTruthy();
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function setText(text: string) {
  const view = EditorView.findFromDOM(document.querySelector('[role="dialog"] .cm-editor')!)!;
  act(() => view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } }));
}
async function save() {
  await act(async () => click(button("rework.create") ?? button("rework.save")));
}
beforeEach(async () => {
  vi.resetAllMocks();
  context = SPACES;
  stamp = 1;
  route.teamId = SPACE_A;
  promptBReady = false;
  catalogError = false;
  createCalls.length = 0;
  createRejectsWith = null;
  deleteRejectsWith = null;
  confirmation.last = null;
  authorize.mockImplementation(() => ({ unwrap: async () => ({ allowed: true }), abort: vi.fn() }));
  create.mockImplementation((arg: unknown) => {
    createCalls.push(arg);
    return {
      unwrap: async () => {
        if (createRejectsWith) throw createRejectsWith;
        return PROMPT_DETAIL;
      },
    };
  });
  update.mockImplementation(() => ({ unwrap: async () => PROMPT_DETAIL }));
  remove.mockImplementation(() => ({
    unwrap: async () => {
      if (deleteRejectsWith) throw deleteRejectsWith;
    },
  }));
  copy.mockResolvedValue(true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<PromptsPage />));
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PromptsPage edit form reseed", () => {
  it("re-populates the form when the same card is reopened after closing via Escape", () => {
    act(() => {
      root.render(<PromptsPage />);
    });

    // Card click now opens the read-only view dialog — reach the edit form
    // through the card's more-menu → "Edit" item instead (the pencil became a
    // more-menu with the prompts marketplace, PROMPT-06). The menu renders in a
    // portal on document.body, so the Edit item is queried from the document.
    const openEditForm = (index = 0) => cardAction("edit", index);

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

    act(() => {
      root.render(<PromptsPage />);
    });

    const openEditForm = (index = 0) => cardAction("edit", index);

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
  it("opens a read-only view dialog instead of the edit form", () => {
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

describe("PromptsPage view dialog", () => {
  const openCard = (index: number) => {
    act(() => {
      root.render(<PromptsPage />);
    });
    const card = container.querySelectorAll('[role="button"]')[index] as HTMLElement;
    act(() => {
      card.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    return document.querySelector('[role="dialog"]') as HTMLElement;
  };

  it("shows the command ahead of the description", () => {
    const dialog = openCard(0);

    // The order is the point: the same reading as the composer's command menu
    // and the panel a command turn opens.
    expect(dialog.textContent).toContain("/summary");
    expect(dialog.textContent!.indexOf("/summary")).toBeLessThan(dialog.textContent!.indexOf("Real description"));
  });

  it("shows nothing of the sort on a prompt that carries no command", () => {
    act(() =>
      root.render(
        <PromptViewDialog
          open
          onClose={() => {}}
          preloadedDetail={{ id: "legacy", name: "Other Name", text: "Other prompt text", command: null }}
        />,
      ),
    );
    const dialog = document.querySelector('[role="dialog"]')!;
    expect(dialog.textContent).toContain("Other prompt text");
    expect(dialog.textContent).not.toContain("/summary");
  });
});

describe("PromptsPage command field", () => {
  const openCreateForm = () => {
    click(button("rework.teams.prompts.create"));
    typeInto(fieldByLabel("form.name")!, "Valid title");
    expect(button("rework.create")?.disabled).toBe(true);
  };

  it("keeps an invalid uppercase name visible and prevents saving", () => {
    openCreateForm();
    const command = fieldByLabel("weaverPrompts.logicalName")!;
    typeInto(command, "S");
    expect(fieldByLabel("weaverPrompts.logicalName")!.value).toBe("S");
    expect(button("rework.create")?.disabled).toBe(true);
  });

  it("rejects a space, an accented letter and punctuation without repairing them", () => {
    openCreateForm();
    const command = fieldByLabel("weaverPrompts.logicalName")!;
    typeInto(command, "abc");
    expect(button("rework.create")?.disabled).toBe(false);
    for (const keystroke of ["abc ", "abcé", "abc!"]) {
      typeInto(fieldByLabel("weaverPrompts.logicalName")!, keystroke);
      expect(fieldByLabel("weaverPrompts.logicalName")!.value).toBe(keystroke);
      expect(button("rework.create")?.disabled).toBe(true);
    }
  });

  it("keeps digits, hyphens and underscores", () => {
    openCreateForm();
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "synthese_v2-bis");
    expect(fieldByLabel("weaverPrompts.logicalName")!.value).toBe("synthese_v2-bis");
    expect(button("rework.create")?.disabled).toBe(false);
  });

  it("sends the command with the create payload", async () => {
    openCreateForm();
    typeInto(fieldByLabel("form.name")!, "Weekly");
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "weekly");
    setText("body");
    await save();
    expect(createCalls).toHaveLength(1);
    expect((createCalls[0] as { createPromptRequest: { logical_name: string } }).createPromptRequest.logical_name).toBe(
      "weekly",
    );
    expect(toast.showSuccess).toHaveBeenLastCalledWith({ summary: "rework.teams.prompts.toasts.created" });
  });

  it("reports a failed save with a translated toast", async () => {
    createRejectsWith = { status: 500, data: { detail: "boom" } };
    openCreateForm();
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "weekly");
    typeInto(fieldByLabel("form.name")!, "Weekly");
    setText("body");
    await save();
    expect(toast.showError).toHaveBeenLastCalledWith({
      summary: "rework.weaverAgents.errors.server",
    });
  });

  it("marks only logical_name when the backend reports prompt_name_conflict", async () => {
    createRejectsWith = { status: 409, data: { code: "prompt_name_conflict", detail: "taken" } };
    openCreateForm();
    typeInto(fieldByLabel("form.name")!, "Weekly");
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "weekly");
    setText("body");
    await save();
    // The form stays open on the conflict so the value can be corrected.
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    const dialogText = document.querySelector('[role="dialog"]')?.textContent ?? "";
    expect(dialogText).toContain("weaverPrompts.nameConflict");
    expect(fieldByLabel("weaverPrompts.logicalName")?.getAttribute("aria-invalid")).toBe("true");
    expect(fieldByLabel("form.name")?.getAttribute("aria-invalid")).not.toBe("true");
    expect(toast.showError).not.toHaveBeenCalled();
  });
});

describe("PromptsPage delete", () => {
  const askToDelete = () => cardAction("delete");

  it("asks for confirmation with translated wording", () => {
    askToDelete();
    expect(confirmation.last).toMatchObject({
      title: "rework.teams.prompts.deleteDialog.title",
      message: "rework.teams.prompts.deleteDialog.message",
      confirmButtonLabel: "rework.teams.prompts.deleteDialog.confirm",
    });
  });

  it("reports a deletion with a translated toast", async () => {
    askToDelete();
    await act(async () => {
      await confirmation.last?.onConfirm();
    });
    expect(toast.showSuccess).toHaveBeenLastCalledWith({ summary: "rework.teams.prompts.toasts.deleted" });
  });

  it("reports a failed deletion with a translated toast", async () => {
    deleteRejectsWith = { status: 500, data: { detail: "boom" } };
    askToDelete();
    await act(async () => {
      await confirmation.last?.onConfirm();
    });
    expect(toast.showError).toHaveBeenLastCalledWith({
      summary: "rework.weaverAgents.errors.server",
    });
  });
});

describe("Weaver prompt management", () => {
  it("uses the canonical personal space for the alias and asks the server for Write", async () => {
    route.teamId = "personal";
    await act(async () => render());
    expect(catalogRead).toHaveBeenLastCalledWith({ spaceId: SPACE_B });
    expect(authorize).toHaveBeenLastCalledWith({ spaceCheck: { space_id: SPACE_B, permission: "write" } });
    expect(container.textContent).toContain("rework.teams.prompts.titlePersonal");
  });

  it("does not inherit a form or Write permission across spaces, even with an owner role", async () => {
    cardAction("edit");
    typeInto(fieldByLabel("form.name")!, "Unsaved draft");
    let allow!: (value: { allowed: boolean }) => void;
    const abort = vi.fn();
    authorize.mockImplementationOnce(() => ({
      unwrap: () =>
        new Promise((resolve) => {
          allow = resolve;
        }),
      abort,
    }));
    context = SPACES.map((space) => ({ ...space, roles: ["owner"] }));
    route.teamId = SPACE_B;
    render();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(button("rework.teams.prompts.create")).toBeUndefined();
    await act(async () => allow({ allowed: false }));
    expect(button("rework.teams.prompts.create")).toBeUndefined();
    route.teamId = SPACE_A;
    await act(async () => render());
    expect(abort).toHaveBeenCalledOnce();
    click(button("rework.teams.prompts.create"));
    expect(formValues()).toEqual({ name: "", description: "", text: "" });
  });

  it("revokes editing immediately while refreshed server authority is unresolved", async () => {
    cardAction("edit");
    let answer!: (value: { allowed: boolean }) => void;
    authorize.mockImplementationOnce(() => ({
      unwrap: () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
      abort: vi.fn(),
    }));
    stamp++;
    render();
    expect(button("rework.save")?.disabled).toBe(true);
    await act(async () => answer({ allowed: false }));
    expect(fieldByLabel("form.name")?.disabled).toBe(true);
    await save();
    expect(update).not.toHaveBeenCalled();
  });

  it("copies the complete text and never the catalog preview", async () => {
    click(container.querySelector('[role="button"]'));
    expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain(PROMPT_DETAIL.text_preview);
    await act(async () => click(document.querySelector('[aria-label="rework.teams.prompts.view.copyAria"]')));
    expect(copy).toHaveBeenCalledExactlyOnceWith("", PROMPT_DETAIL.text);
  });

  it("keeps logical identity immutable and sends only useful PATCH fields", async () => {
    cardAction("edit");
    expect(fieldByLabel("weaverPrompts.logicalName")?.readOnly).toBe(true);
    typeInto(fieldByLabel("form.name")!, "Independent title");
    await save();
    const args = update.mock.calls[0][0];
    expect(args).toMatchObject({ spaceId: SPACE_A, promptId: PROMPT_DETAIL.prompt_id });
    expect(JSON.parse(JSON.stringify(args.updatePromptRequest))).toEqual({ display_name: "Independent title" });
  });

  it("preserves all prompt whitespace and explicitly clears the description", async () => {
    cardAction("edit");
    typeInto(fieldByLabel("form.description")!, "");
    setText("  Instructions 👋\n\n");
    await save();
    expect(JSON.parse(JSON.stringify(update.mock.calls[0][0].updatePromptRequest))).toEqual({
      text: "  Instructions 👋\n\n",
      description: null,
    });
  });

  it("requires a new logical identity for duplication while preserving title and full text", async () => {
    cardAction("duplicate");
    expect(fieldByLabel("weaverPrompts.logicalName")?.value).toBe("");
    const confirm = () => button("rework.teams.prompts.duplicateDialog.confirm");
    expect(confirm()?.disabled).toBe(true);
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "Summary");
    expect(confirm()?.disabled).toBe(true);
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "summary-copy");
    await act(async () => click(confirm()));
    expect(create).toHaveBeenCalledExactlyOnceWith({
      spaceId: SPACE_A,
      createPromptRequest: {
        logical_name: "summary-copy",
        display_name: PROMPT_DETAIL.display_name,
        description: PROMPT_DETAIL.description,
        text: PROMPT_DETAIL.text,
      },
    });
  });

  it.each(["title", "description"])("counts Unicode code points at the %s boundary", (field) => {
    click(button("rework.teams.prompts.create"));
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "valid");
    typeInto(fieldByLabel("form.name")!, "Title");
    const label = field === "title" ? "form.name" : "form.description";
    const limit = field === "title" ? 255 : 500;
    typeInto(fieldByLabel(label)!, "👋".repeat(limit));
    expect(button("rework.create")?.disabled).toBe(false);
    typeInto(fieldByLabel(label)!, "👋".repeat(limit + 1));
    expect(button("rework.create")?.disabled).toBe(true);
    if (field === "title") {
      typeInto(fieldByLabel(label)!, "e\u0301".repeat(limit));
      expect(button("rework.create")?.disabled).toBe(false);
    }
  });

  it.each(["success", "conflict"])("ignores a late create %s after closing and reopening", async (outcome) => {
    let resolve!: (value: unknown) => void;
    let reject!: (reason: unknown) => void;
    create.mockImplementationOnce(() => ({
      unwrap: () =>
        new Promise((yes, no) => {
          resolve = yes;
          reject = no;
        }),
    }));
    click(button("rework.teams.prompts.create"));
    typeInto(fieldByLabel("form.name")!, "Old title");
    typeInto(fieldByLabel("weaverPrompts.logicalName")!, "old");
    await save();
    escape();
    click(button("rework.teams.prompts.create"));
    typeInto(fieldByLabel("form.name")!, "New draft");
    await act(async () =>
      outcome === "success" ? resolve(PROMPT_DETAIL) : reject({ status: 409, data: { code: "prompt_name_conflict" } }),
    );
    expect(formValues().name).toBe("New draft");
    expect(document.body.textContent).not.toContain("weaverPrompts.nameConflict");
    expect(toast.showSuccess).not.toHaveBeenCalled();
    expect(toast.showError).not.toHaveBeenCalled();
  });

  it.each(["before", "during"])("ignores deletion when navigation happens %s the request", async (when) => {
    let finish!: () => void;
    remove.mockImplementationOnce(() => ({
      unwrap: () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    }));
    cardAction("delete");
    expect(remove).not.toHaveBeenCalled();
    let pending: unknown;
    if (when === "during")
      act(() => {
        pending = confirmation.last!.onConfirm();
      });
    route.teamId = SPACE_B;
    await act(async () => render());
    if (when === "before") {
      await act(async () => {
        await confirmation.last!.onConfirm();
      });
      expect(remove).not.toHaveBeenCalled();
    } else {
      await act(async () => {
        finish();
        await pending;
      });
      expect(remove).toHaveBeenCalledExactlyOnceWith({ spaceId: SPACE_A, promptId: PROMPT_DETAIL.prompt_id });
    }
    expect(toast.showSuccess).not.toHaveBeenCalled();
    expect(toast.showError).not.toHaveBeenCalled();
  });

  it("does not display catalog rows after a failed refresh", () => {
    catalogError = true;
    render();
    expect(container.querySelector('[role="button"]')).toBeNull();
    expect(container.textContent).toContain("rework.weaverPrompts.catalogError");
  });
});
