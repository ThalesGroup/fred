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

// `t` keeps its interpolation options: the chip's whole visible output is a
// NUMBER, so a stub that drops {{count}} would make every count assertion
// vacuous.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
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
//   Broken  → doc-broken + doc-ok
//   Done    → doc-done + doc-idle
// The last two folders hold TWO documents each on purpose: a single-document
// subtree cannot tell "any child finished" from "every child finished", nor a
// per-document precedence rule from a per-folder one.
const TAGS = [
  { id: "tag-live", name: "Live", path: "", type: "document", item_ids: ["doc-live"] },
  { id: "tag-nested", name: "Nested", path: "", type: "document", item_ids: [] },
  { id: "tag-deep", name: "Deep", path: "Nested", type: "document", item_ids: ["doc-deep"] },
  { id: "tag-broken", name: "Broken", path: "", type: "document", item_ids: ["doc-broken", "doc-ok"] },
  { id: "tag-done", name: "Done", path: "", type: "document", item_ids: ["doc-done", "doc-idle"] },
  // Enough documents to exercise the hover panel's cap.
  {
    id: "tag-bulk",
    name: "Bulk",
    path: "",
    type: "document",
    item_ids: Array.from({ length: 13 }, (_, i) => `doc-bulk-${i}`),
  },
];

// `tasks` is the whole store (selectAllTasks); `selectActiveTasks` is derived
// from it exactly as the real selector does — by dropping terminal states — so
// a test can never hand the component a "failed active task", which the real
// app cannot produce either.
const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
let tasks: ReturnType<typeof task>[] = [];
// What `GET /tasks?scope=team&state=…` returns. Deliberately separate from
// `tasks`: after a page reload the Redux store is empty and this is the ONLY
// feed left, which is exactly the case that used to leave the Corpus root
// looking clean while folders below it held failures.
let taskHistory: {
  state: string;
  error?: string | null;
  target: { type: string; id: string; label: string };
  updated_at: string;
}[] = [];
// The args the workspace asked the history with — asserted directly, since a
// regression there (wrong scope, missing kind) is invisible in the rendered row.
let taskHistoryArgs: Record<string, unknown> = {};
const historyEntry = (uid: string, state: string, label: string, updatedAt: string) => ({
  state,
  error: null as string | null,
  target: { type: "document", id: uid, label },
  updated_at: updatedAt,
});

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
  // The team's terminal ingestion history (#2384) — what survives a page
  // reload. ONE unfiltered call: a team-scoped query already returns every
  // state, so the args are asserted rather than used to filter.
  useListTasksKnowledgeFlowV1TasksGetQuery: (arg: Record<string, unknown>) => {
    taskHistoryArgs = arg;
    return { data: { tasks: taskHistory } };
  },
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
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({}) })),
  ],
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
// The shared clipboard write every copy site in the app routes through (#2366).
vi.mock("../../../../utils/clipboardUtils", () => ({ writeRichClipboard: vi.fn(async () => true) }));

import { writeRichClipboard } from "../../../../utils/clipboardUtils";
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

/** Hovers a folder's rollup chip and returns the portaled tooltip's text. The
 *  folder list is scanned at a glance, so it stays a hover panel — unlike the
 *  per-stage error on a document row, which is click-opened to be copyable.
 *  React derives onMouseEnter from the bubbling `mouseover` (see Tooltip.test). */
function openChip(row: HTMLElement): string {
  const chip = [...row.querySelectorAll("span")].find((el) => el.textContent?.includes(FAILED_COUNT));
  if (!chip) throw new Error("failure chip not rendered on this row");
  act(() => {
    chip.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  });
  const panel = document.querySelector('[role="tooltip"]');
  if (!panel) throw new Error("detail panel did not open");
  return panel.textContent ?? "";
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
  taskHistory = [];
  taskHistoryArgs = {};
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
    expect(openChip(row)).toContain("Broken report.pdf");
  });

  it("marks a folder done once something under it finished and nothing is left running or failed", async () => {
    // "Done" also holds doc-idle, which was never ingested this session. The
    // mark means "what you started here has landed", not "every document in
    // this folder was processed" — a folder of long-stored documents would
    // never qualify under the stricter reading, and the transient mark exists
    // precisely to answer "did my upload finish?".
    tasks = [task("t-done", "doc-done", "succeeded", "Done doc.pdf")];
    await renderWorkspace();

    expect(folderRow("Done").textContent).toContain(JUST_DONE);
  });

  it("clears a failure once the same document is re-ingested successfully", async () => {
    // A document uid is derived from content, so re-uploading a file that
    // failed produces a SECOND task for the same uid. Nothing removes the old
    // one from the store (taskEvicted is only dispatched by the unmounted
    // TaskTray), so only the latest terminal task may count — otherwise the
    // folder stays flagged for the rest of the session with no way to clear it.
    tasks = [
      { ...task("t-broken", "doc-broken", "failed", "Broken report.pdf"), terminalAt: 1000 },
      { ...task("t-retry", "doc-broken", "succeeded", "Broken report.pdf"), terminalAt: 2000 },
    ];
    await renderWorkspace();

    expect(folderRow("Broken").textContent).not.toContain(FAILED_COUNT);
    expect(folderRow("Broken").textContent).toContain(JUST_DONE);
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
    // Two different documents in one folder: one landed, one did not. The
    // unresolved failure is the more actionable of the two, so it wins.
    tasks = [
      task("t-broken", "doc-broken", "failed", "Broken report.pdf"),
      task("t-ok", "doc-ok", "succeeded", "Fine.pdf"),
    ];
    await renderWorkspace();

    expect(folderRow("Broken").textContent).toContain(FAILED_COUNT);
    expect(folderRow("Broken").textContent).not.toContain(JUST_DONE);
  });

  it("does not flag a cancelled ingestion as a failure", async () => {
    // Stopping an ingestion on purpose is neither an error to chase nor a
    // completion to celebrate.
    tasks = [task("t-cancel", "doc-broken", "cancelled", "Broken report.pdf")];
    await renderWorkspace();

    expect(folderRow("Broken").textContent).not.toContain("rework.resources.status");
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
    expect(openChip(row)).toContain("Snapshot.pdf");
  });

  it("still counts failures after a reload, from the team history alone", async () => {
    // No live tasks at all — the Redux store is empty on a fresh page load, and
    // GET /tasks?scope=user hides terminal tasks. Before the team-scoped
    // history was merged in, the Corpus root went blank on refresh and the
    // badge only came back once the user opened the folder.
    taskHistory = [historyEntry("doc-broken", "failed", "Broken report.pdf", "2026-08-17T10:00:00Z")];
    await renderWorkspace();

    const row = folderRow("Broken");
    expect(row.textContent).toContain(FAILED_COUNT);
    expect(openChip(row)).toContain("Broken report.pdf");
  });

  it("surfaces a teammate's failure, which the user-scoped feed can never see", async () => {
    // doc-deep sits two levels down and was ingested by someone else: nothing
    // in this browser session knows about it.
    taskHistory = [historyEntry("doc-deep", "failed", "Collegue.pdf", "2026-08-17T10:00:00Z")];
    await renderWorkspace();

    expect(folderRow("Nested").textContent).toContain(FAILED_COUNT);
  });

  it("does not resurrect a failure the history also reports as later fixed", async () => {
    // Why both states are fetched: re-uploading a file produces a second task
    // for the same uid, and a `failed`-only query would keep flagging a folder
    // the user has already repaired, on every reload, forever.
    taskHistory = [
      historyEntry("doc-broken", "failed", "Broken report.pdf", "2026-08-17T10:00:00Z"),
      historyEntry("doc-broken", "succeeded", "Broken report.pdf", "2026-08-17T11:00:00Z"),
    ];
    await renderWorkspace();

    expect(folderRow("Broken").textContent).not.toContain(FAILED_COUNT);
  });

  it("lets an in-session outcome override the history it was loaded with", async () => {
    // The history is a snapshot taken at mount; a run that finishes afterwards
    // arrives over SSE and must win.
    taskHistory = [historyEntry("doc-broken", "failed", "Broken report.pdf", "2026-08-17T10:00:00Z")];
    tasks = [
      {
        ...task("t-fix", "doc-broken", "succeeded", "Broken report.pdf"),
        terminalAt: Date.parse("2026-08-17T12:00:00Z"),
      },
    ];
    await renderWorkspace();

    expect(folderRow("Broken").textContent).not.toContain(FAILED_COUNT);
    expect(folderRow("Broken").textContent).toContain(JUST_DONE);
  });

  it("never marks a folder done from the history alone", async () => {
    // The `succeeded` history is fetched ONLY to outrank a stale failure. Were
    // it folded into the just-finished set, every document the team has ever
    // ingested would count, turning a transient "your upload landed" cue into a
    // permanent green tick on every folder and every ready row (#2315).
    taskHistory = [historyEntry("doc-done", "succeeded", "Done doc.pdf", "2026-08-17T10:00:00Z")];
    await renderWorkspace();

    expect(folderRow("Done").textContent).not.toContain(JUST_DONE);
    expect(folderRow("Done").textContent).not.toContain("rework.resources.status");
  });

  it("asks for the team's ingestion history in one unfiltered call", async () => {
    // A team-scoped query already returns every state (exclude_terminal only
    // defaults to hiding them on the `user` branch), so filtering by state would
    // cost a second round-trip and drop `cancelled` plus teammates' in-flight
    // runs. Asserted here because none of it is visible in the rendered row.
    await renderWorkspace();

    expect(taskHistoryArgs).toEqual({ scope: "team", teamId: "team-1", kind: "ingestion" });
    expect(taskHistoryArgs.state).toBeUndefined();
  });

  it("counts every failure under the folder, not just one", async () => {
    tasks = [task("t-1", "doc-broken", "failed", "Broken report.pdf"), task("t-2", "doc-ok", "failed", "Fine.pdf")];
    await renderWorkspace();

    expect(folderRow("Broken").textContent).toContain(`${FAILED_COUNT}:{"count":2}`);
  });

  it("names the first ten failures and summarizes the rest", async () => {
    // The hover panel is portaled outside the chip, so its scrollbar is
    // unreachable — an uncapped list would be clipped with no way to read past
    // the fold.
    taskHistory = Array.from({ length: 13 }, (_, i) =>
      historyEntry(`doc-bulk-${i}`, "failed", `Bulk-${i}.pdf`, "2026-08-17T10:00:00Z"),
    );
    await renderWorkspace();

    const row = folderRow("Bulk");
    expect(row.textContent).toContain(`${FAILED_COUNT}:{"count":13}`);
    const panel = openChip(row);
    expect(panel).toContain("Bulk-0.pdf");
    expect(panel).toContain("Bulk-9.pdf");
    expect(panel).not.toContain("Bulk-10.pdf");
    expect(panel).toContain(`folderFailedMore:{"count":3}`);
  });

  it("copies every failure, including the ones the panel only summarizes", async () => {
    // The rendered list stops at ten; the clipboard must not. Copying is
    // precisely when the whole list is wanted — a support ticket, or a message
    // to whoever uploaded them. Reachable at all only because the panel is
    // interactive: a plain tooltip would vanish before the pointer got there.
    const written: string[] = [];
    vi.mocked(writeRichClipboard).mockImplementation(async (_html: string, text: string) => {
      written.push(text);
      return true;
    });
    taskHistory = Array.from({ length: 13 }, (_, i) =>
      historyEntry(`doc-bulk-${i}`, "failed", `Bulk-${i}.pdf`, "2026-08-17T10:00:00Z"),
    );
    await renderWorkspace();
    openChip(folderRow("Bulk"));

    const copyButton = document.querySelector('[role="tooltip"] button');
    if (!copyButton) throw new Error("copy button not rendered");
    await click(copyButton);

    expect(written).toHaveLength(1);
    expect(written[0].split("\n")).toHaveLength(13);
    expect(written[0]).toContain("Bulk-12.pdf");
  });

  it("shows the task's own error on a document whose failure never reached a stage", async () => {
    // The gap this closes: a run killed before any pipeline stage started
    // stamps nothing in `processing.errors`, so the Resources tab used to show
    // "Erreur" with an empty panel while the message sat on the task, visible
    // only in the task popover. The parent workflow already extracts it from
    // the Temporal child job (#2315).
    snapshotDoc = { stage: "failed" };
    taskHistory = [
      { ...historyEntry("doc-snapshot", "failed", "Snapshot.pdf", "2026-08-17T10:00:00Z"), error: "Worker timed out" },
    ];
    await renderWorkspace();
    await click(folderRow("Broken").querySelector("button")!);

    const chip = [...container.querySelectorAll('[class*="chip"]')].find((el) =>
      el.textContent?.includes("rework.resources.status.failed"),
    );
    if (!chip) throw new Error("failed chip not rendered");
    act(() => {
      chip.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });

    const panel = document.querySelector('[role="tooltip"]');
    expect(panel!.textContent).toContain("Worker timed out");
  });

  it("shows nothing anywhere when no document has any state to report", async () => {
    await renderWorkspace();

    for (const name of ["Live", "Nested", "Broken", "Done"]) {
      expect(folderRow(name).textContent).not.toContain("rework.resources.status");
    }
  });
});
