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

// Coverage (#2384): a FOLDER row must carry the "processing" chip while any
// document under it is still ingesting — including one buried several levels
// down — so the top of the tree answers "is the bulk upload finished?" without
// walking into every sub-folder. Two invariants the implementation must keep:
// the chip is driven by NON-TERMINAL tasks only (a folder therefore never
// aggregates failure — a failed child leaves the folder silent, its error
// stays on the document's own row), and a folder with no live child shows
// nothing at all rather than a "ready" chip.

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
vi.mock("react-redux", () => ({ useSelector: (selector: () => unknown) => selector() }));

const task = (taskId: string, documentUid: string, state: string) => ({
  taskId,
  kind: "ingestion",
  target: { type: "document", id: documentUid, label: `${documentUid}.pdf` },
  owner: null,
  localOnly: false,
  state,
  progress: 0.5,
  step: "processing",
  error: null,
  lastSeq: 1,
  registeredAt: 0,
  terminalAt: null,
  acknowledgedAt: null,
  warnings: null,
});

// Corpus root holds three folders:
//   Live     → its own doc-live is ingesting            → chip
//   Nested   → nothing of its own, but Nested/Deep/doc-deep is ingesting → chip
//   Settled  → doc-failed's task already reached "failed" (so it is NOT in the
//              active feed at all)                       → no chip, ever
const TAGS = [
  { id: "tag-live", name: "Live", path: "", type: "document", item_ids: ["doc-live"] },
  { id: "tag-nested", name: "Nested", path: "", type: "document", item_ids: [] },
  { id: "tag-deep", name: "Deep", path: "Nested", type: "document", item_ids: ["doc-deep"] },
  { id: "tag-settled", name: "Settled", path: "", type: "document", item_ids: ["doc-failed"] },
];

// Mirrors selectActiveTasks, which filters out every terminal state — the
// failed task is deliberately absent, not present-with-state-failed.
let activeTasks: ReturnType<typeof task>[] = [];

// A document the browse snapshot alone reports as processing: a stage left
// `in_progress` with NO live task behind it (dead worker, or a teammate's
// ingestion — the task feed is scope=user). Served for "Settled" only.
const snapshotProcessingDoc = {
  identity: { document_uid: "doc-stuck", title: "Stuck", document_name: "Stuck.pdf", uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: false },
  processing: { stages: { vector: "in_progress" } },
  tags: { tag_ids: ["tag-settled"] },
};
let servePages = false;

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({ data: TAGS, isLoading: false, refetch: () => {} }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    (arg: { browseDocumentsByTagRequest: { tag_id: string } }) => ({
      unwrap: async () =>
        servePages && arg.browseDocumentsByTagRequest.tag_id === "tag-settled"
          ? { documents: [snapshotProcessingDoc], total: 1 }
          : { documents: [], total: 0 },
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [
    () => ({ unwrap: async () => ({ sizes: {} }) }),
  ],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({
  selectActiveTasks: () => activeTasks,
  selectAllTasks: () => [],
}));
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

// The name button's textContent also carries the folder Icon's own ligature
// text ("folder"), so this matches on containment, not equality.
function folderRow(name: string): HTMLElement {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
  if (!button) throw new Error(`"${name}" folder row not rendered`);
  const row = button.closest('[class*="datatable-row"]');
  if (!row) throw new Error(`"${name}" row container not found`);
  return row as HTMLElement;
}

async function renderWorkspace(): Promise<void> {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });
}

beforeEach(() => {
  activeTasks = [];
  servePages = false;
});

async function click(el: Element): Promise<void> {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocumentWorkspace — folder rows reflect their subtree's live ingestions (#2384)", () => {
  it("badges a folder whose own document is ingesting", async () => {
    activeTasks = [task("t-live", "doc-live", "running")];
    await renderWorkspace();

    expect(folderRow("Live").textContent).toContain("rework.resources.status.processing");
  });

  it("badges an ancestor folder whose ingesting document sits in a sub-folder", async () => {
    // "Nested" holds no document of its own — only "Nested/Deep" does. This is
    // the whole point of the feature: the answer must be visible from the top.
    activeTasks = [task("t-deep", "doc-deep", "pending")];
    await renderWorkspace();

    expect(folderRow("Nested").textContent).toContain("rework.resources.status.processing");
  });

  it("leaves folders with no live child completely silent", async () => {
    activeTasks = [task("t-live", "doc-live", "running")];
    await renderWorkspace();

    // Settled's only document has a FAILED task (absent from the active feed):
    // a folder never aggregates failure, and never shows a "ready" chip either.
    expect(folderRow("Settled").textContent).not.toContain("rework.resources.status");
    expect(folderRow("Nested").textContent).not.toContain("rework.resources.status");
  });

  it("shows nothing anywhere once every ingestion has settled", async () => {
    await renderWorkspace();

    for (const name of ["Live", "Nested", "Settled"]) {
      expect(folderRow(name).textContent).not.toContain("rework.resources.status");
    }
  });

  it("badges a visited folder whose loaded page shows a processing row with no live task", async () => {
    // The task feed is scope=user, so it never sees a teammate's ingestion (nor
    // a document a dead worker left `in_progress`). A folder must not read
    // "settled" while a row the user has already loaded inside it visibly spins.
    servePages = true;
    await renderWorkspace();

    await click(folderRow("Settled").querySelector("button")!);
    expect(container.textContent).toContain("rework.resources.status.processing");

    const back = container.querySelector('[aria-label="rework.resources.action.back"]');
    if (!back) throw new Error("back button not rendered");
    await click(back);

    expect(folderRow("Settled").textContent).toContain("rework.resources.status.processing");
    expect(folderRow("Live").textContent).not.toContain("rework.resources.status");
  });
});
