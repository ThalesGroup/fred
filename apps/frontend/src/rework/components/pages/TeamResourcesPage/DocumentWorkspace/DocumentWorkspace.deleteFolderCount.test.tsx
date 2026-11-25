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

import { act, type ReactNode } from "react";
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
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn(), useSelector: () => [] }));

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
const initialTags = () => [
  { id: "tag-documents", name: "Documents", path: "", type: "document", item_ids: ["d-1", "d-2", "d-3", "d-4"] },
  { id: "tag-dossier-112", name: "Dossier 112", path: "Documents", type: "document", item_ids: ["d-5"] },
  { id: "tag-hr", name: "HR", path: "", type: "document", item_ids: ["d-6"] },
];
let tags = initialTags();
const renameFolder = vi.fn(async (_node: { full: string }, newName: string) => {
  tags = tags.map((tag) =>
    tag.id === "tag-documents" ? { ...tag, name: newName } : tag.path === "Documents" ? { ...tag, path: newName } : tag,
  );
});
const deleteTag = vi.fn(({ tagId }: { tagId: string }) => ({
  unwrap: async () => {
    if (tagId === "tag-documents") tags = tags.filter((tag) => tag.id === "tag-hr");
    return {};
  },
}));

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListTagsQuery: () => ({ data: tags, isLoading: false, refetch: () => {} }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [browseDocumentsByTag],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagMutation: () => [vi.fn()],
  useDeleteTagMutation: () => [deleteTag],
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
    renameFolder,
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
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({
  InlineDrawer: ({ layout, children }: { layout?: string; children?: ReactNode }) =>
    layout === "rail" ? <>{children}</> : null,
}));

import DocumentWorkspace from "./DocumentWorkspace";
import { setCurrentUserPreferences } from "../../../../../app/userPreferences";

let container: HTMLDivElement;
let root: Root;

beforeEach(async () => {
  setCurrentUserPreferences({});
  browseFails = false;
  browseDocumentsByTag.mockClear();
  showConfirmationDialog.mockClear();
  deleteTag.mockClear();
  renameFolder.mockClear();
  tags = initialTags();
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
  const label = [...container.querySelectorAll<HTMLElement>("[data-row-activation]")].find((node) =>
    node.textContent?.includes(name),
  );
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

async function openFolder(name: string) {
  const row = [...container.querySelectorAll<HTMLElement>("[data-row-activation]")].find((node) =>
    node.textContent?.includes(name),
  );
  if (!row) throw new Error(`folder ${name} not rendered`);
  await act(async () => {
    row.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    await Promise.resolve();
  });
}

async function openTree() {
  const opener = container.querySelector<HTMLButtonElement>('button[aria-label="rework.resources.tree.openPanel"]');
  if (!opener) throw new Error("tree opener not rendered");
  await act(async () => opener.click());
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

  it("returns to the corpus root when deleting an ancestor of the viewed folder from the tree", async () => {
    await openFolder("Documents");
    await openFolder("Dossier 112");
    await openTree();
    expect(container.querySelector('nav button[aria-current="page"]')?.getAttribute("title")).toBe("Dossier 112");

    const ancestor = container.querySelector<HTMLButtonElement>('nav button[title="Documents"]');
    if (!ancestor) throw new Error("ancestor folder not rendered");
    await act(async () => ancestor.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    const deleteItem = [...document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')].find((button) =>
      button.textContent?.includes("rework.resources.action.delete"),
    );
    if (!deleteItem) throw new Error("tree delete action not rendered");
    await act(async () => deleteItem.click());
    expect(showConfirmationDialog).toHaveBeenCalled();
    await act(async () => {
      showConfirmationDialog.mock.lastCall?.[0].onConfirm();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.querySelector('nav button[aria-current="page"]')?.getAttribute("title")).toBe(
      "rework.resources.roots.resources",
    );
    expect(container.textContent).not.toContain("Dossier 112");
  });

  it("keeps the viewed descendant under its new path after renaming an ancestor from the tree", async () => {
    await openFolder("Documents");
    await openFolder("Dossier 112");
    await openTree();
    const ancestor = container.querySelector<HTMLButtonElement>('nav button[title="Documents"]');
    if (!ancestor) throw new Error("ancestor folder not rendered");
    await act(async () => ancestor.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    const renameItem = [...document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')].find((button) =>
      button.textContent?.includes("rework.resources.action.rename"),
    );
    if (!renameItem) throw new Error("tree rename action not rendered");
    await act(async () => renameItem.click());

    const input = document.querySelector<HTMLInputElement>('[role="dialog"] input');
    if (!input) throw new Error("rename input not rendered");
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(input, "Archives");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const save = [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find((button) =>
      button.textContent?.includes("rework.resources.renameModal.save"),
    );
    if (!save) throw new Error("rename save action not rendered");
    await act(async () => {
      save.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(renameFolder).toHaveBeenCalledWith(expect.objectContaining({ full: "Documents" }), "Archives");
    expect(container.querySelector('nav button[title="Archives"]')).not.toBeNull();
    expect(container.querySelector('nav button[aria-current="page"]')?.getAttribute("title")).toBe("Dossier 112");
    expect(container.querySelector('nav button[title="Documents"]')).toBeNull();
  });

  it("promises no number rather than a wrong one when the count cannot be fetched", async () => {
    browseFails = true;

    await clickDeleteOnFolder("Documents");

    expect(dialogMessage()).toContain("deleteFolderMessageUnknownCount");
  });

  it("shows an unknown count without requesting every tag in a large subtree", async () => {
    tags = [
      ...initialTags(),
      ...Array.from({ length: 25 }, (_, index) => ({
        id: `tag-extra-${index}`,
        name: `Extra ${index}`,
        path: "Documents",
        type: "document",
        item_ids: [],
      })),
    ];
    await act(async () => root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />));
    browseDocumentsByTag.mockClear();

    await clickDeleteOnFolder("Documents");

    expect(dialogMessage()).toContain("deleteFolderMessageUnknownCount");
    expect(browseDocumentsByTag).not.toHaveBeenCalled();
  });
});
