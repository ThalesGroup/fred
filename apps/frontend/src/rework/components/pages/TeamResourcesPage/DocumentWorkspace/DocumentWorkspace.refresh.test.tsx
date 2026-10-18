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

// The toolbar's refresh control. The knowledge-flow cache serves the previous
// answer for a short window rather than refetching on every mount, which is
// what makes returning to this page instant — this button is how you force the
// round trip when you know the data moved under you.

import "./inactiveManagerFolders.test-support";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  refetchTags: vi.fn(() => Promise.resolve({ data: [] })),
  browse: vi.fn(() => ({
    unwrap: () =>
      probe.browseResponses.shift() ?? Promise.resolve({ documents: probe.documents, total: probe.documents.length }),
  })),
  browseResponses: [] as Promise<{ documents: unknown[]; total: number }>[],
  canUpdateResources: true,
  documents: [] as unknown[],
  tags: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
  onTasksSettled: (_documentUids: string[]) => {},
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn(), useSelector: () => [] }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListTagsQuery: () => ({
    data: probe.tags,
    isLoading: false,
    refetch: probe.refetchTags,
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [probe.browse],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({ sizes: {} }) })),
  ],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagMutation: () => [vi.fn()],
  useDeleteTagMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({}) })),
  ],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [], selectAllTasks: () => [] }));
vi.mock("../../../../features/tasks/useRefetchOnTaskSettled", () => ({
  useRefetchOnTaskSettled: (_type: string, onSettled: (documentUids: string[]) => void) => {
    probe.onTasksSettled = onSettled;
  },
}));
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
  useTeamCapabilities: () => ({ canUpdateResources: probe.canUpdateResources }),
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
let documentsChanged: number;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <DocumentWorkspace teamId="team-1" isPersonalTeam={false} onDocumentsChanged={() => (documentsChanged += 1)} />,
    );
  });
}

beforeEach(() => {
  probe.refetchTags.mockClear();
  probe.browse.mockClear();
  probe.canUpdateResources = true;
  probe.documents = [];
  probe.tags = [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }];
  probe.browseResponses.length = 0;
  documentsChanged = 0;
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function refreshButton(): HTMLButtonElement | null {
  return container.querySelector('button[aria-label="rework.resources.action.refresh"]');
}

function folderButton(name: string): HTMLButtonElement {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
  if (!button) throw new Error(`folder row "${name}" not rendered`);
  return button;
}

function deferredBrowse() {
  let resolve!: (value: { documents: unknown[]; total: number }) => void;
  const promise = new Promise<{ documents: unknown[]; total: number }>((done) => {
    resolve = done;
  });
  probe.browseResponses.push(promise);
  return resolve;
}

function doc(uid: string) {
  return {
    identity: { document_uid: uid, title: uid, document_name: `${uid}.pdf`, uploaded_by: null },
    file: { file_type: "pdf", file_size_bytes: 1024 },
    source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
    processing: { stages: { raw: "done" } },
    tags: { tag_ids: ["tag-cir"] },
  };
}

describe("DocumentWorkspace refresh action", () => {
  it("refetches the folder tree, the usage stats and the storage quota", async () => {
    render();
    // refetchTags carries onDocumentsChanged, which is what refreshes the
    // corpus stats and the team's quota meter — one press updates the lot.
    probe.refetchTags.mockClear();
    const changedBefore = documentsChanged;

    click(refreshButton());
    await act(async () => {});

    expect(probe.refetchTags).toHaveBeenCalledTimes(1);
    expect(documentsChanged).toBe(changedBefore + 1);
  });

  it("reloads the open folder's page as well as the tree", async () => {
    render();
    click(folderButton("CIR"));
    await act(async () => {});
    probe.browse.mockClear();

    click(refreshButton());
    await act(async () => {});

    expect(probe.browse).toHaveBeenCalledWith({
      browseDocumentsByTagRequest: expect.objectContaining({ tag_id: "tag-cir" }),
    });
  });

  it("stays available to a member who cannot write", () => {
    // Refreshing is not a mutation. The two actions next to it are gated on the
    // write capability; this one must not be.
    probe.canUpdateResources = false;
    render();

    expect(refreshButton()).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.menu.newFolder"]')).toBeNull();
  });

  it("reloads a folder once when several of its documents settle together", async () => {
    probe.documents = [doc("uid-1"), doc("uid-2")];
    render();
    click(folderButton("CIR"));
    await act(async () => {});
    probe.browse.mockClear();
    const changedBefore = documentsChanged;

    await act(async () => probe.onTasksSettled(["uid-1", "uid-2"]));

    expect(probe.browse).toHaveBeenCalledTimes(1);
    expect(documentsChanged).toBe(changedBefore + 1);
  });

  it("shows loading until the first folder browse succeeds", async () => {
    const finishBrowse = deferredBrowse();
    render();
    click(folderButton("CIR"));

    expect(container.textContent).toContain("rework.resources.loading");
    expect(container.textContent).not.toContain("rework.resources.empty.folder");

    await act(async () => finishBrowse({ documents: [], total: 0 }));
    expect(container.textContent).toContain("rework.resources.empty.folder");
  });

  it("explains a failed first browse and lets Refresh retry it", async () => {
    let failBrowse!: (reason: Error) => void;
    probe.browseResponses.push(
      new Promise<{ documents: unknown[]; total: number }>((_resolve, reject) => {
        failBrowse = reject;
      }),
    );
    render();
    click(folderButton("CIR"));

    await act(async () => failBrowse(new Error("Network unavailable")));
    expect(container.textContent).toContain("rework.resources.empty.loadError");
    expect(container.textContent).not.toContain("rework.resources.empty.folder");

    click(refreshButton());
    await act(async () => {});
    expect(container.textContent).toContain("rework.resources.empty.folder");
  });

  it("keeps child folders visible when the parent document browse fails", async () => {
    probe.tags = [
      { id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] },
      { id: "tag-sub", name: "Sub", path: "CIR", type: "document", item_ids: [] },
    ];
    let failBrowse!: (reason: Error) => void;
    probe.browseResponses.push(
      new Promise<{ documents: unknown[]; total: number }>((_resolve, reject) => {
        failBrowse = reject;
      }),
    );
    render();
    click(folderButton("CIR"));

    await act(async () => failBrowse(new Error("Network unavailable")));
    expect(container.textContent).toContain("Sub");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("rework.resources.empty.loadError");
  });

  it("ignores an older empty browse that finishes after a newer populated browse", async () => {
    probe.documents = [doc("uid-1")];
    render();
    click(folderButton("CIR"));
    await act(async () => {});
    expect(container.textContent).toContain("uid-1.pdf");

    const finishOldBrowse = deferredBrowse();
    const finishNewBrowse = deferredBrowse();
    await act(async () => {
      probe.onTasksSettled(["uid-1"]);
      probe.onTasksSettled(["uid-1"]);
    });

    await act(async () => finishNewBrowse({ documents: [doc("uid-1"), doc("uid-2")], total: 2 }));
    expect(container.textContent).toContain("uid-2.pdf");

    await act(async () => finishOldBrowse({ documents: [], total: 0 }));
    expect(container.textContent).toContain("uid-1.pdf");
    expect(container.textContent).toContain("uid-2.pdf");
    expect(container.textContent).not.toContain("rework.resources.empty.folder");
  });
});
