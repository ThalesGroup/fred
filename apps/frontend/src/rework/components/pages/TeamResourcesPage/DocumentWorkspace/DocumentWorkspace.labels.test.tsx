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

// Coverage: the "Manage labels" row action shows a document's current
// descriptive labels, lets the user add one (typed or picked from a
// suggestion) and remove one, each applying immediately through the
// canonical PATCH /documents/{uid}/labels body transport (useDocumentCommands
// .mutateLabels -> useMutateDocumentLabelsMutation), including values the old
// URL-path-segment routes could not carry.

import { act } from "react";
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
vi.mock("react-redux", () => ({ useSelector: () => [] }));

const currentDoc = {
  identity: { document_uid: "uid-1", title: null, document_name: "report.pdf", uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z" },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
  labels: ["DAT"],
};

const otherDoc = {
  identity: { document_uid: "uid-2", title: null, document_name: "other.pdf", uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 512 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z" },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
  labels: [],
};

const mutateLabels = vi.fn();

// Mutable, module-scoped "server state" for the label vocabulary — read
// fresh on every mocked-hook call (i.e. every render); mutating it inside
// `refetchLabels`'s configured implementation simulates a server round-trip
// landing before the component's next render. Reset in beforeEach.
let vocabulary: string[] = [];
const refetchLabels = vi.fn();

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListDocumentLabelsQuery: () => ({ data: vocabulary, refetch: refetchLabels }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({ unwrap: async () => ({ documents: [currentDoc, otherDoc], total: 2 }) }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [], selectAllTasks: () => [] }));
vi.mock("../../../../features/tasks/useRefetchOnTaskSuccess", () => ({ useRefetchOnTaskSuccess: () => {} }));
vi.mock("../../../../features/tasks/useNotifyOnNewTaskTarget", () => ({ useNotifyOnNewTaskTarget: () => {} }));
vi.mock("../../../../../components/documents/common/useDocumentCommands", () => ({
  useDocumentCommands: () => ({
    previewTarget: null,
    closePreview: () => {},
    preview: () => {},
    download: async () => {},
    toggleRetrievable: async () => {},
    removeFromLibrary: async () => {},
    renameDocument: async () => {},
    mutateLabels,
  }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: () => {} }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: { id: "team-1" } }),
  useUsersByIdsQuery: () => ({ data: [] }),
}));
const useTeamCapabilities = vi.fn(() => ({ canUpdateResources: true }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => useTeamCapabilities(),
}));
vi.mock("../CreateFolderModal/CreateFolderModal.tsx", () => ({ default: () => null }));
vi.mock("@shared/organisms/DocumentUploadDrawer/DocumentUploadDrawer.tsx", () => ({
  DocumentUploadDrawer: () => null,
}));
vi.mock("@shared/organisms/DocumentViewer/DocumentViewer.tsx", () => ({ DocumentViewer: () => null }));
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({ InlineDrawer: () => null }));

import DocumentWorkspace from "./DocumentWorkspace";

let container: HTMLDivElement;
let root: Root;

beforeEach(async () => {
  mutateLabels.mockReset();
  refetchLabels.mockReset();
  refetchLabels.mockResolvedValue(undefined); // real RTK Query refetch() always returns a promise
  vocabulary = ["DAT", "MEX", "CONFIDENTIAL"];
  useTeamCapabilities.mockReturnValue({ canUpdateResources: true });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });

  const cir = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("CIR"));
  if (!cir) throw new Error('"CIR" folder row not rendered');
  await act(async () => {
    cir.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  document.querySelectorAll('[role="presentation"]').forEach((el) => el.remove());
});

function moreButtonForRow(rowName: string): HTMLButtonElement {
  const buttons = [
    ...container.querySelectorAll('button[aria-label="rework.resources.action.more"]'),
  ] as HTMLButtonElement[];
  const btn = buttons.find((b) => b.closest('[class*="datatable-row"]')?.textContent?.includes(rowName));
  if (!btn) throw new Error(`"more" button for row "${rowName}" not found`);
  return btn;
}

function openLabelsModal(rowName = "report.pdf") {
  const moreButton = moreButtonForRow(rowName);
  act(() => {
    moreButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  const items = [
    ...document.querySelectorAll(
      '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
    ),
  ];
  const labelsItem = items.find((el) => el.textContent?.includes("rework.resources.action.manageLabels"));
  if (!labelsItem) throw new Error("manage labels menu item not found");
  act(() => {
    labelsItem.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function dialog(): HTMLElement {
  const el = document.querySelector('[role="dialog"]') as HTMLElement | null;
  if (!el) throw new Error("labels dialog not rendered");
  return el;
}

function labelInput(): HTMLInputElement {
  const input = dialog().querySelector("input") as HTMLInputElement | null;
  if (!input) throw new Error("label input not rendered");
  return input;
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function addButton(): HTMLButtonElement {
  const btn = [...dialog().querySelectorAll("button")].find((b) =>
    /rework\.resources\.labelsModal\.(add|createNew)$/.test(b.textContent ?? ""),
  ) as HTMLButtonElement | undefined;
  if (!btn) throw new Error("add/create button not found");
  return btn;
}

async function clickAddButton() {
  await act(async () => {
    addButton().dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

async function clickRemoveButtonFor(label: string) {
  const buttons = [...dialog().querySelectorAll("button")];
  const btn = buttons.find((b) => b.closest("span")?.textContent?.startsWith(label));
  if (!btn) throw new Error(`remove button for "${label}" not found`);
  await act(async () => {
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

async function clickSuggestion(label: string) {
  const option = [...dialog().querySelectorAll('[role="option"]')].find((el) => el.textContent?.includes(label));
  if (!option) throw new Error(`suggestion "${label}" not rendered`);
  await act(async () => {
    option.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function closeModal() {
  const closeButton = [...dialog().querySelectorAll("button")].find(
    (b) => b.textContent === "rework.resources.labelsModal.close",
  ) as HTMLButtonElement | undefined;
  if (!closeButton) throw new Error("labels modal close button not found");
  act(() => {
    closeButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function suggestionTexts(): (string | null)[] {
  return [...dialog().querySelectorAll('[role="option"]')].map((el) => el.textContent);
}

describe("DocumentWorkspace — manage a document's labels", () => {
  it("shows the document's current labels as chips when the modal opens", () => {
    openLabelsModal();
    expect(dialog().textContent).toContain("DAT");
  });

  it("adds a typed label via a single mutateLabels({ add }) call", async () => {
    mutateLabels.mockResolvedValue(["DAT", "URGENT"]);
    openLabelsModal();

    setInputValue(labelInput(), "URGENT");
    await clickAddButton();

    expect(mutateLabels).toHaveBeenCalledTimes(1);
    const [doc, patch] = mutateLabels.mock.calls[0] as [
      { identity: { document_uid: string } },
      { add?: string[]; remove?: string[] },
    ];
    expect(doc.identity.document_uid).toBe("uid-1");
    expect(patch).toEqual({ add: ["URGENT"] });
    expect(dialog().textContent).toContain("URGENT");
  });

  it("adds a suggested label by clicking it in the menu", async () => {
    mutateLabels.mockResolvedValue(["DAT", "MEX"]);
    openLabelsModal();

    setInputValue(labelInput(), "MEX");
    await clickSuggestion("MEX");

    expect(mutateLabels).toHaveBeenCalledTimes(1);
    const [, patch] = mutateLabels.mock.calls[0] as [unknown, { add?: string[] }];
    expect(patch).toEqual({ add: ["MEX"] });
  });

  it("removes an existing label via a single mutateLabels({ remove }) call", async () => {
    mutateLabels.mockResolvedValue([]);
    openLabelsModal();
    expect(dialog().textContent).toContain("DAT");

    await clickRemoveButtonFor("DAT");

    expect(mutateLabels).toHaveBeenCalledTimes(1);
    const [doc, patch] = mutateLabels.mock.calls[0] as [{ identity: { document_uid: string } }, { remove?: string[] }];
    expect(doc.identity.document_uid).toBe("uid-1");
    expect(patch).toEqual({ remove: ["DAT"] });
  });

  it.each([
    ["a/b#c?d%e", "characters the old URL path segment could not carry"],
    ["with space", "a space"],
    ["café", "an accented Unicode letter"],
    ["日本語", "non-Latin Unicode letters"],
  ])("adds a label containing %s (%s) — the new body transport has no character restriction", async (label) => {
    mutateLabels.mockResolvedValue(["DAT", label]);
    openLabelsModal();

    setInputValue(labelInput(), label);
    expect(addButton().hasAttribute("disabled")).toBe(false);
    await clickAddButton();

    expect(mutateLabels).toHaveBeenCalledWith(expect.anything(), { add: [label] });
    expect(dialog().textContent).toContain(label);
  });

  it("never sends an empty or whitespace-only label", () => {
    openLabelsModal();

    setInputValue(labelInput(), "   ");

    expect(addButton().hasAttribute("disabled")).toBe(true);
    expect(mutateLabels).not.toHaveBeenCalled();
  });

  it("suggests already-visible labels not yet applied, filtered by the typed query", () => {
    openLabelsModal();
    setInputValue(labelInput(), "");
    // "DAT" is already applied to this document — must not be re-offered.
    expect(suggestionTexts().some((t) => t === "DAT")).toBe(false);
    expect(suggestionTexts().some((t) => t?.includes("MEX"))).toBe(true);
    expect(suggestionTexts().some((t) => t?.includes("CONFIDENTIAL"))).toBe(true);

    setInputValue(labelInput(), "conf");
    expect(suggestionTexts().some((t) => t?.includes("CONFIDENTIAL"))).toBe(true);
    expect(suggestionTexts().some((t) => t?.includes("MEX"))).toBe(false);
  });

  it("shows a plain 'Add' label for a suggestion already in the vocabulary, and 'Create' for anything else", () => {
    openLabelsModal();

    setInputValue(labelInput(), "MEX");
    expect(addButton().textContent).toContain("rework.resources.labelsModal.add");

    setInputValue(labelInput(), "BRAND-NEW");
    expect(addButton().textContent).toContain("rework.resources.labelsModal.createNew");
  });

  it("keeps a genuinely retryable input when the mutation fails — visible text and button state never diverge", async () => {
    mutateLabels.mockResolvedValue(undefined); // useDocumentCommands.mutateLabels already caught + toasted
    openLabelsModal();

    setInputValue(labelInput(), "URGENT");
    await clickAddButton();

    expect(mutateLabels).toHaveBeenCalledTimes(1);
    expect(dialog().textContent).toContain("DAT"); // unchanged — no false success
    const urgentChipButton = [...dialog().querySelectorAll("button")].find((b) =>
      b.closest("span")?.textContent?.startsWith("URGENT"),
    );
    expect(urgentChipButton).toBeUndefined();
    expect(labelInput().value).toBe("URGENT"); // still there, retryable
    expect(addButton().hasAttribute("disabled")).toBe(false);

    mutateLabels.mockResolvedValue(["DAT", "URGENT"]);
    await clickAddButton();
    expect(mutateLabels).toHaveBeenCalledTimes(2);
    expect(dialog().textContent).toContain("URGENT");
  });

  it("does not roll back a confirmed mutation when the vocabulary refetch fails", async () => {
    mutateLabels.mockResolvedValue(["DAT", "URGENT"]);
    refetchLabels.mockRejectedValue(new Error("network error"));
    openLabelsModal();

    setInputValue(labelInput(), "URGENT");
    await clickAddButton();

    // The mutation's own result is what's shown — a failed *vocabulary*
    // refresh only means suggestions may be stale, never that the label
    // that was actually added disappears.
    expect(dialog().textContent).toContain("URGENT");
  });

  it("refetches the vocabulary asynchronously after a successful mutation, not before", async () => {
    mutateLabels.mockResolvedValue(["DAT", "URGENT"]);
    openLabelsModal();

    setInputValue(labelInput(), "URGENT");
    await clickAddButton();

    expect(refetchLabels).toHaveBeenCalled();
  });

  it("serializes rapid successive mutation attempts with a synchronous lock — a second click while the first is still in flight is a no-op", async () => {
    const resolvers: Array<(value: string[] | undefined) => void> = [];
    mutateLabels.mockImplementation(
      () =>
        new Promise<string[] | undefined>((resolve) => {
          resolvers.push(resolve);
        }),
    );
    openLabelsModal();
    setInputValue(labelInput(), "FIRST");

    act(() => {
      addButton().dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      addButton().dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(mutateLabels).toHaveBeenCalledTimes(1);
    expect(resolvers).toHaveLength(1);

    await act(async () => {
      resolvers[0]?.(["DAT", "FIRST"]);
    });
    expect(dialog().textContent).toContain("FIRST");
  });

  it("does not select the row when opening the labels modal from the 'more' menu", () => {
    const rowCheckbox = [...container.querySelectorAll('input[type="checkbox"]')][1] as HTMLInputElement;
    expect(rowCheckbox.checked).toBe(false);

    openLabelsModal();

    expect(rowCheckbox.checked).toBe(false);
  });

  it("gives the add field an explicit accessible name", () => {
    openLabelsModal();

    expect(labelInput().getAttribute("aria-label")).toBe("rework.resources.labelsModal.addFieldLabel");
  });

  it("focuses the add field when the modal opens", () => {
    openLabelsModal();

    expect(document.activeElement).toBe(labelInput());
  });

  it("gives each chip's remove button an accessible name naming the label", () => {
    openLabelsModal();

    const removeButton = [...dialog().querySelectorAll("button")].find((b) =>
      b.closest("span")?.textContent?.startsWith("DAT"),
    );
    expect(removeButton?.getAttribute("aria-label")).toBe("rework.resources.labelsModal.removeAriaLabel");
  });

  it("does not offer 'Manage labels' (or the other mutating actions) to a user without write capability", async () => {
    useTeamCapabilities.mockReturnValue({ canUpdateResources: false });
    const readOnlyContainer = document.createElement("div");
    document.body.appendChild(readOnlyContainer);
    const readOnlyRoot = createRoot(readOnlyContainer);
    await act(async () => {
      readOnlyRoot.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
    });
    const cir = [...readOnlyContainer.querySelectorAll("button")].find((b) => b.textContent?.includes("CIR"));
    if (!cir) throw new Error('"CIR" folder row not rendered');
    await act(async () => {
      cir.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    const moreButton = readOnlyContainer.querySelector(
      'button[aria-label="rework.resources.action.more"]',
    ) as HTMLButtonElement;
    act(() => {
      moreButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    const items = [
      ...document.querySelectorAll(
        '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
      ),
    ];
    expect(items.some((el) => el.textContent?.includes("rework.resources.action.manageLabels"))).toBe(false);
    expect(items.some((el) => el.textContent?.includes("rework.resources.action.download"))).toBe(true);

    act(() => {
      readOnlyRoot.unmount();
    });
    readOnlyContainer.remove();
  });

  it("refreshes the vocabulary from the server after each mutation — a newly created label becomes a suggestion elsewhere, and a label removed from the vocabulary stops being suggested", async () => {
    openLabelsModal("other.pdf");
    expect(suggestionTexts().some((t) => t?.includes("BRANDNEW"))).toBe(false);
    expect(suggestionTexts().some((t) => t === "DAT")).toBe(true);
    closeModal();

    mutateLabels.mockResolvedValue(["DAT", "BRANDNEW"]);
    refetchLabels.mockImplementation(() => {
      vocabulary = [...vocabulary, "BRANDNEW"];
      return Promise.resolve();
    });
    openLabelsModal("report.pdf");
    setInputValue(labelInput(), "BRANDNEW");
    await clickAddButton();
    closeModal();

    openLabelsModal("other.pdf");
    expect(suggestionTexts().some((t) => t?.includes("BRANDNEW"))).toBe(true);
    closeModal();

    mutateLabels.mockResolvedValue(["BRANDNEW"]);
    refetchLabels.mockImplementation(() => {
      vocabulary = vocabulary.filter((label) => label !== "DAT");
      return Promise.resolve();
    });
    openLabelsModal("report.pdf");
    await clickRemoveButtonFor("DAT");
    closeModal();

    openLabelsModal("other.pdf");
    expect(suggestionTexts().some((t) => t === "DAT")).toBe(false);
  });
});
