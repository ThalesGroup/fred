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

// Coverage (#2384): a FOLDER row summarizes the ingestion state of its whole
// subtree — processing / some failed / all just finished — so the top of the
// tree answers "did my bulk upload land?" without walking into every
// sub-folder. What these tests pin down:
//  - the rollup reaches documents buried several levels down;
//  - precedence is processing > failures > done (still running is not settled;
//    once settled, an unresolved failure outranks a "your upload landed" mark);
//  - the two evidence sources are genuinely independent — the session task feed
//    reaches never-opened folders, the loaded-page snapshot survives a reload
//    and sees what the user-scoped feed cannot;
//  - failures are named, not just counted.

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

const task = (taskId: string, documentUid: string, state: string, label: string) => ({
  taskId,
  kind: "ingestion",
  target: { type: "document", id: documentUid, label },
  owner: null,
  localOnly: false,
  state,
  progress: 0.5,
  step: "processing",
  error: state === "failed" ? "boom" : null,
  lastSeq: 1,
  registeredAt: 0,
  terminalAt: state === "running" ? null : 1,
  acknowledgedAt: null,
  warnings: null,
});

// Corpus root holds four folders:
//   Live    → its own doc-live                      (task fixtures decide)
//   Nested  → nothing of its own; Nested/Deep holds doc-deep
//   Broken  → doc-broken
//   Done    → doc-done
const TAGS = [
  { id: "tag-live", name: "Live", path: "", type: "document", item_ids: ["doc-live"] },
  { id: "tag-nested", name: "Nested", path: "", type: "document", item_ids: [] },
  { id: "tag-deep", name: "Deep", path: "Nested", type: "document", item_ids: ["doc-deep"] },
  { id: "tag-broken", name: "Broken", path: "", type: "document", item_ids: ["doc-broken"] },
  { id: "tag-done", name: "Done", path: "", type: "document", item_ids: ["doc-done"] },
];

// `tasks` is the whole store (selectAllTasks); `selectActiveTasks` is derived
// from it exactly as the real selector does — by dropping terminal states — so
// a test can never hand the component a "failed active task", which the real
// app cannot produce either.
const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
let tasks: ReturnType<typeof task>[] = [];

// A document the browse snapshot alone reports on, with no task behind it at
// all: a stage left `in_progress`/`failed` by a dead worker, or a teammate's
// ingestion (the task feed is scope=user). Served for "Broken" only, and only
// once a test opts in — this is the source that survives a page reload.
let snapshotDoc: { stage: string } | null = null;
const snapshotPage = (stage: string) => ({
  identity: { document_uid: "doc-snapshot", title: "Snap", document_name: "Snapshot.pdf", uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: false },
  processing: { stages: { vector: stage } },
  tags: { tag_ids: ["tag-broken"] },
});

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({ data: TAGS, isLoading: false, refetch: () => {} }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    (arg: { browseDocumentsByTagRequest: { tag_id: string } }) => ({
      unwrap: async () =>
        snapshotDoc && arg.browseDocumentsByTagRequest.tag_id === "tag-broken"
          ? { documents: [snapshotPage(snapshotDoc.stage)], total: 1 }
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
  selectActiveTasks: () => tasks.filter((t) => !TERMINAL.has(t.state)),
  selectAllTasks: () => tasks,
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

const PROCESSING = "rework.resources.status.processing";
const FAILED_COUNT = "rework.resources.status.folderFailed";
const JUST_DONE = "rework.resources.status.justDone";

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

async function click(el: Element): Promise<void> {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

/** Hovers a folder's rollup chip and returns the portaled tooltip's text.
 *  React derives onMouseEnter from the bubbling `mouseover` (see Tooltip.test). */
function hoverChip(row: HTMLElement): string {
  const chip = [...row.querySelectorAll("span")].find((el) => el.textContent?.includes(FAILED_COUNT));
  if (!chip) throw new Error("failure chip not rendered on this row");
  act(() => {
    chip.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  });
  const tooltip = document.querySelector('[role="tooltip"]');
  if (!tooltip) throw new Error("tooltip did not open");
  return tooltip.textContent ?? "";
}

/** Opens a folder and comes straight back, leaving its page loaded in `perTag`. */
async function visitAndReturn(name: string): Promise<void> {
  await click(folderRow(name).querySelector("button")!);
  const back = container.querySelector('[aria-label="rework.resources.action.back"]');
  if (!back) throw new Error("back button not rendered");
  await click(back);
}

beforeEach(() => {
  tasks = [];
  snapshotDoc = null;
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocumentWorkspace — folder rows roll up their subtree (#2384)", () => {
  it("badges a folder whose own document is ingesting", async () => {
    tasks = [task("t-live", "doc-live", "running", "Live doc.pdf")];
    await renderWorkspace();

    expect(folderRow("Live").textContent).toContain(PROCESSING);
  });

  it("badges an ancestor folder whose ingesting document sits in a sub-folder", async () => {
    // "Nested" holds no document of its own — only "Nested/Deep" does. This is
    // the whole point of the feature: the answer must be visible from the top.
    tasks = [task("t-deep", "doc-deep", "pending", "Deep doc.pdf")];
    await renderWorkspace();

    expect(folderRow("Nested").textContent).toContain(PROCESSING);
  });

  it("leaves an untouched folder completely silent", async () => {
    tasks = [task("t-live", "doc-live", "running", "Live doc.pdf")];
    await renderWorkspace();

    expect(folderRow("Nested").textContent).not.toContain("rework.resources.status");
    expect(folderRow("Done").textContent).not.toContain("rework.resources.status");
  });

  it("counts a failed document and names it on hover", async () => {
    tasks = [task("t-broken", "doc-broken", "failed", "Broken report.pdf")];
    await renderWorkspace();

    const row = folderRow("Broken");
    expect(row.textContent).toContain(FAILED_COUNT);
    expect(row.textContent).not.toContain(PROCESSING);
    // The name comes from the task's own target label — no request, and it
    // works for a folder the user has never opened.
    expect(hoverChip(row)).toContain("Broken report.pdf");
  });

  it("marks a folder done for the session once its documents have succeeded", async () => {
    tasks = [task("t-done", "doc-done", "succeeded", "Done doc.pdf")];
    await renderWorkspace();

    expect(folderRow("Done").textContent).toContain(JUST_DONE);
  });

  it("keeps processing ahead of a failure while anything is still running", async () => {
    // A batch where one file already failed and another is still going: the
    // folder is not settled yet, so the spinner outranks the failure count.
    tasks = [
      task("t-live", "doc-live", "running", "Live doc.pdf"),
      task("t-live-2", "doc-live", "failed", "Live doc.pdf"),
    ];
    await renderWorkspace();

    expect(folderRow("Live").textContent).toContain(PROCESSING);
    expect(folderRow("Live").textContent).not.toContain(FAILED_COUNT);
  });

  it("keeps a failure ahead of done once everything has settled", async () => {
    tasks = [
      task("t-broken", "doc-broken", "failed", "Broken report.pdf"),
      task("t-broken-2", "doc-broken", "succeeded", "Broken report.pdf"),
    ];
    await renderWorkspace();

    expect(folderRow("Broken").textContent).toContain(FAILED_COUNT);
    expect(folderRow("Broken").textContent).not.toContain(JUST_DONE);
  });

  it("badges a visited folder whose loaded page shows a processing row with no live task", async () => {
    // The task feed is scope=user, so it never sees a teammate's ingestion (nor
    // a document a dead worker left `in_progress`). A folder must not read
    // "settled" while a row the user has already loaded inside it visibly spins.
    snapshotDoc = { stage: "in_progress" };
    await renderWorkspace();
    await visitAndReturn("Broken");

    expect(folderRow("Broken").textContent).toContain(PROCESSING);
  });

  it("counts a failure the snapshot reports with no task behind it, naming the document", async () => {
    // The persistent half of the rollup: this is what still shows after a page
    // reload, when `GET /tasks?scope=user` has stopped returning terminal tasks.
    snapshotDoc = { stage: "failed" };
    await renderWorkspace();
    await visitAndReturn("Broken");

    const row = folderRow("Broken");
    expect(row.textContent).toContain(FAILED_COUNT);
    expect(hoverChip(row)).toContain("Snapshot.pdf");
  });

  it("shows nothing anywhere when no document has any state to report", async () => {
    await renderWorkspace();

    for (const name of ["Live", "Nested", "Broken", "Done"]) {
      expect(folderRow(name).textContent).not.toContain("rework.resources.status");
    }
  });
});
