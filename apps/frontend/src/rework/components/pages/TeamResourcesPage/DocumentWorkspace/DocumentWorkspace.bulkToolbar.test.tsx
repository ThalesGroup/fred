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

// Coverage for the toolbar swap: "Nouveau dossier"/"Ajouter des fichiers" are
// not useful once the user is selecting rows to bulk-act on, so the bulk
// actions bar (delete/exclude) replaces them entirely instead of the two
// sitting side by side, for as long as at least one row is selected.

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

const doc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z" },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
});

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({ unwrap: async () => ({ documents: [doc("uid-1", "Report")], total: 1 }) }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
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
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });

  // Navigate into "CIR" — its documents only load once it's the current folder.
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
});

function rowCheckbox(): HTMLInputElement {
  // [0] is the header's "select all"; [1] is the one doc row in this fixture.
  const boxes = [...container.querySelectorAll('input[type="checkbox"]')];
  const box = boxes[1];
  if (!box) throw new Error("row checkbox not rendered");
  return box as HTMLInputElement;
}

describe("DocumentWorkspace toolbar — bulk actions replace new-folder/add-file while selecting", () => {
  it("hides new-folder/add-file and shows bulk actions once a row is selected", () => {
    expect(container.querySelector('button[aria-label="rework.resources.menu.newFolder"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).toBeNull();

    act(() => {
      rowCheckbox().click();
    });

    expect(container.querySelector('button[aria-label="rework.resources.menu.newFolder"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).not.toBeNull();
    expect(
      container.querySelector('button[aria-label="rework.resources.bulkActions.excludeFromSearch"]'),
    ).not.toBeNull();
  });

  it("restores new-folder/add-file once the selection is cleared", () => {
    act(() => {
      rowCheckbox().click();
    });
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).not.toBeNull();

    act(() => {
      rowCheckbox().click(); // untoggle
    });

    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.menu.newFolder"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).not.toBeNull();
  });
});
