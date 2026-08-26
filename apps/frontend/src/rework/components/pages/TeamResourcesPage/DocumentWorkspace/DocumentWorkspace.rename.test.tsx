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

// Coverage: renaming a document from the row "more" menu calls the real
// rename mutation (DOCUMENT-RENAME-RFC.md), not the old cosmetic title edit,
// and the row reflects the new name after the modal's own refresh.

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
};

const renameDocument = vi.fn();

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({ unwrap: async () => ({ documents: [currentDoc], total: 1 }) }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({}) })),
  ],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [], selectAllTasks: () => [] }));
vi.mock("../../../../features/tasks/useRefetchOnTaskSettled", () => ({ useRefetchOnTaskSettled: () => {} }));
vi.mock("../../../../features/tasks/useNotifyOnNewTaskTarget", () => ({ useNotifyOnNewTaskTarget: () => {} }));
vi.mock("../../../../../components/documents/common/useDocumentCommands", () => ({
  useDocumentCommands: () => ({
    previewTarget: null,
    closePreview: () => {},
    preview: () => {},
    download: async () => {},
    toggleRetrievable: async () => {},
    removeFromLibrary: async () => {},
    renameDocument,
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
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canUpdateResources: true }),
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
  renameDocument.mockClear();
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

function openRenameModal() {
  const moreButton = container.querySelector('button[aria-label="rework.resources.action.more"]') as HTMLButtonElement;
  act(() => {
    moreButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  const items = [
    ...document.querySelectorAll(
      '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
    ),
  ];
  const renameItem = items.find((el) => el.textContent?.includes("rework.resources.action.rename"));
  if (!renameItem) throw new Error("rename menu item not found");
  act(() => {
    renameItem.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function renameInput(): HTMLInputElement {
  const input = document.querySelector('[role="dialog"] input') as HTMLInputElement | null;
  if (!input) throw new Error("rename input not rendered");
  return input;
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function clickSave() {
  const saveButton = [...document.querySelectorAll('[role="dialog"] button')].find((b) =>
    b.textContent?.includes("rework.resources.renameModal.save"),
  ) as HTMLButtonElement;
  await act(async () => {
    saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("DocumentWorkspace — rename a document", () => {
  it("opens the modal pre-filled with only the base name — the extension is locked, not part of the editable value", () => {
    openRenameModal();
    expect(renameInput().value).toBe("report");
  });

  it("shows the locked extension next to the input, outside the editable value", () => {
    openRenameModal();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog?.textContent).toContain(".pdf");
    expect(renameInput().value).not.toContain(".pdf");
  });

  it("calls the real rename command with the typed base plus the locked extension re-appended", async () => {
    openRenameModal();
    setInputValue(renameInput(), "Q3-Final");
    await clickSave();

    expect(renameDocument).toHaveBeenCalledTimes(1);
    const [doc, newName, tagId] = renameDocument.mock.calls[0] as [
      { identity: { document_uid: string } },
      string,
      string | undefined,
    ];
    expect(doc.identity.document_uid).toBe("uid-1");
    expect(newName).toBe("Q3-Final.pdf");
    // #2407: the folder being viewed must be passed through - without it the
    // command's refresh() cannot reload this page and the row keeps the old
    // name even though the rename succeeded server-side.
    expect(tagId).toBe("tag-cir");
  });

  it("does not select the row when clicking a 'more' menu item — the menu portals to document.body, and React bubbles portal clicks through the React tree, not the DOM tree, so the row's own click-to-select guard can't see them via target.closest()", () => {
    // [0] is the header's "select all"; [1] is this row's own checkbox.
    const rowCheckbox = [...container.querySelectorAll('input[type="checkbox"]')][1] as HTMLInputElement;
    expect(rowCheckbox.checked).toBe(false);

    openRenameModal();

    expect(rowCheckbox.checked).toBe(false);
  });
});
