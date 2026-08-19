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

// Coverage: how many documents the "delete folder" confirmation announces.
// It used to read the cached tag list's `item_ids`, which is wrong twice over.
// Too high — `item_ids` only refreshes when this workspace itself mutates
// something, so documents the backend removed on its own (a cancelled ingestion
// erasing its half-built document, the OPS-04 sweeper) stayed counted: a folder
// showing one document announced four. Too low — it covers the folder's own
// documents only, while `delete_tag` recurses into every sub-tag, so a folder
// with subfolders under-announced what it was about to destroy.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Interpolation values matter here (the announced count is one of them), so the
// stub t() keeps them instead of collapsing to the bare key.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));

// Live totals per tag, deliberately disagreeing with the stale `item_ids` below.
const liveTotals: Record<string, number> = { "tag-documents": 1, "tag-dossier-112": 2, "tag-hr": 0 };
let browseFails = false;
const browseDocumentsByTag = vi.fn((arg: { browseDocumentsByTagRequest: { tag_id: string; limit: number } }) => ({
  unwrap: async () => {
    if (browseFails) throw new Error("browse unavailable");
    return { documents: [], total: liveTotals[arg.browseDocumentsByTagRequest.tag_id] ?? 0 };
  },
}));
const showConfirmationDialog = vi.fn();

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [
      // Four ids the workspace was told about at upload time; three of those
      // documents are gone and nothing refreshed this list since.
      {
        id: "tag-documents",
        name: "Documents",
        path: "",
        type: "document",
        item_ids: ["d-1", "d-2", "d-3", "d-4"],
      },
      { id: "tag-dossier-112", name: "Dossier 112", path: "Documents", type: "document", item_ids: ["d-5"] },
      { id: "tag-hr", name: "HR", path: "", type: "document", item_ids: ["d-6"] },
    ],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [browseDocumentsByTag],
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
  useConfirmationDialog: () => ({ showConfirmationDialog }),
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
  browseFails = false;
  browseDocumentsByTag.mockClear();
  showConfirmationDialog.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  document.querySelectorAll('[role="presentation"]').forEach((el) => el.remove());
});

/** Opens the folder row's "more" menu and picks Delete. */
async function clickDeleteOnFolder(name: string) {
  const label = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
  if (!label) throw new Error(`"${name}" folder row not rendered`);
  const row = (label.closest('[role="row"], tr, li') ?? label.parentElement?.parentElement) as HTMLElement;
  const moreButton = row.querySelector('button[aria-label="rework.resources.action.more"]') as HTMLButtonElement;
  if (!moreButton) throw new Error(`"${name}" row has no more menu`);
  await act(async () => {
    moreButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  const items = [
    ...document.querySelectorAll(
      '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
    ),
  ];
  const deleteItem = items.find((el) => el.textContent?.includes("rework.resources.action.delete"));
  if (!deleteItem) throw new Error("delete menu item not found");
  await act(async () => {
    deleteItem.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

const dialogMessage = () => {
  const calls = showConfirmationDialog.mock.calls;
  return calls[calls.length - 1][0].message as string;
};

describe("DocumentWorkspace — documents announced by the delete-folder dialog", () => {
  it("counts what the backend has now, not the stale item_ids the tag list was cached with", async () => {
    await clickDeleteOnFolder("Documents");

    // item_ids says 4 (+1 in the subfolder); the live totals are 1 + 2.
    expect(dialogMessage()).toContain("deleteFolderMessageWithDocs");
    expect(dialogMessage()).toContain('"count":3');
  });

  it("includes the subfolders' documents, which the cascade deletes too", async () => {
    await clickDeleteOnFolder("Documents");

    const askedFor = browseDocumentsByTag.mock.calls.map((c) => c[0].browseDocumentsByTagRequest.tag_id);
    expect(askedFor).toContain("tag-documents");
    expect(askedFor).toContain("tag-dossier-112");
    // A count, not a page of documents, however large the folder is.
    expect(browseDocumentsByTag.mock.calls.every((c) => c[0].browseDocumentsByTagRequest.limit === 1)).toBe(true);
  });

  it("calls a folder empty when the backend says so, even with leftover item_ids", async () => {
    await clickDeleteOnFolder("HR");

    expect(dialogMessage()).toContain("deleteFolderMessageEmpty");
  });

  it("promises no number rather than a wrong one when the count cannot be fetched", async () => {
    browseFails = true;

    await clickDeleteOnFolder("Documents");

    expect(dialogMessage()).toContain("deleteFolderMessageUnknownCount");
  });
});
