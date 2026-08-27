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

// Folder rows drive the same contextual bulk bar as documents (#2446), with
// actions applied recursively to the folder's subtree: delete cascades via
// deleteTag, download resolves descendant docs and zips them under their
// folder-relative path, exclude-from-search forces every descendant document
// non-retrievable. Documents are fetched only when the action fires.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { deleteTagSpy, updateRetrievableSpy, downloadManyAsZipSpy } = vi.hoisted(() => ({
  deleteTagSpy: vi.fn((_arg: { tagId: string }) => ({ unwrap: async () => ({}) })),
  updateRetrievableSpy: vi.fn((_arg: { documentUid: string; retrievable: boolean }) => ({
    unwrap: async () => ({}),
  })),
  downloadManyAsZipSpy: vi.fn(async (_files: { filename: string }[], _zipName: string) => {}),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));

const doc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z" },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-reports"] },
});

// Two-level tree at the corpus root: "Reports" (tag-reports) with a sub-folder
// "2024" (tag-2024). One document lives directly under each tag.
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [
      { id: "tag-reports", name: "Reports", path: "", type: "document", item_ids: [] },
      { id: "tag-2024", name: "2024", path: "Reports", type: "document", item_ids: [] },
    ],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    ({ browseDocumentsByTagRequest }: { browseDocumentsByTagRequest: { tag_id: string } }) => ({
      unwrap: async () => {
        const id = browseDocumentsByTagRequest.tag_id;
        if (id === "tag-reports") return { documents: [doc("uid-root", "RootReport")], total: 1 };
        if (id === "tag-2024") return { documents: [doc("uid-2024", "Report2024")], total: 1 };
        return { documents: [], total: 0 };
      },
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [deleteTagSpy],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    updateRetrievableSpy,
  ],
}));
vi.mock("../../../../../utils/downloadUtils.tsx", () => ({ downloadManyAsZip: downloadManyAsZipSpy }));
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
    bulkRemoveFromLibraryForTag: async () => {},
    fetchBlob: async () => new Blob(),
  }),
}));
// Fire onConfirm synchronously so the delete action actually runs under test.
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({
    showConfirmationDialog: ({ onConfirm }: { onConfirm: () => void }) => onConfirm(),
  }),
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

/** Let the on-click resolver's browse round-trips settle. */
async function flush() {
  await act(async () => {
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

beforeEach(async () => {
  deleteTagSpy.mockClear();
  updateRetrievableSpy.mockClear();
  downloadManyAsZipSpy.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

/** The "Reports" folder row checkbox ([0] is the header select-all). */
function folderCheckbox(): HTMLInputElement {
  const boxes = [...container.querySelectorAll('input[type="checkbox"]')];
  const box = boxes[1];
  if (!box) throw new Error("folder row checkbox not rendered");
  return box as HTMLInputElement;
}

function selectFolder() {
  act(() => folderCheckbox().click());
}

describe("DocumentWorkspace — bulk actions on selected folders (#2446)", () => {
  it("shows the contextual bar (with exclude-from-search) once a folder is selected", () => {
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).toBeNull();

    selectFolder();

    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).not.toBeNull();
    expect(
      container.querySelector('button[aria-label="rework.resources.bulkActions.excludeFromSearch"]'),
    ).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.download"]')).not.toBeNull();
  });

  it("deletes the folder's tag (backend cascades to its subtree) on bulk delete", async () => {
    selectFolder();
    const del = container.querySelector(
      'button[aria-label="rework.resources.bulkActions.delete"]',
    ) as HTMLButtonElement;
    await act(async () => {
      del.click();
    });
    await flush();
    expect(deleteTagSpy).toHaveBeenCalledWith({ tagId: "tag-reports" });
  });

  it("zips every descendant document under its folder-relative path on bulk download", async () => {
    selectFolder();
    const dl = container.querySelector(
      'button[aria-label="rework.resources.bulkActions.download"]',
    ) as HTMLButtonElement;
    await act(async () => {
      dl.click();
    });
    await flush();

    expect(downloadManyAsZipSpy).toHaveBeenCalledTimes(1);
    const [files, zipName] = downloadManyAsZipSpy.mock.calls[0];
    expect(zipName).toBe("resources.zip");
    expect(files.map((f) => f.filename).sort()).toEqual(["Reports/2024/Report2024.pdf", "Reports/RootReport.pdf"]);
  });

  it("forces every descendant document non-retrievable on bulk exclude-from-search", async () => {
    selectFolder();
    const excl = container.querySelector(
      'button[aria-label="rework.resources.bulkActions.excludeFromSearch"]',
    ) as HTMLButtonElement;
    await act(async () => {
      excl.click();
    });
    await flush();

    expect(updateRetrievableSpy).toHaveBeenCalledTimes(2);
    const uids = updateRetrievableSpy.mock.calls.map((c) => c[0].documentUid).sort();
    expect(uids).toEqual(["uid-2024", "uid-root"]);
    for (const call of updateRetrievableSpy.mock.calls) {
      expect(call[0].retrievable).toBe(false);
    }
  });
});
