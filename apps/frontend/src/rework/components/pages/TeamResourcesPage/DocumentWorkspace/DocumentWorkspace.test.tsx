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

// Coverage for OS-file drag-and-drop onto a corpus folder row: dropping files
// must open the ingestion drawer (profile fast/medium/rich) seeded with the
// dropped files and targeting the dropped-on folder, under the same
// CAN_UPDATE_RESOURCES gate as the row's explicit upload action. The drawer is
// mocked as a probe so assertions read the exact props it receives.

import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCurrentUserPreferences } from "../../../../../app/userPreferences.ts";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  drawerProps: [] as Record<string, unknown>[],
  canUpdateResources: true,
  createTagCalls: [] as Record<string, unknown>[],
  browseCalls: [] as { tag_id: string }[],
  docs: [] as unknown[],
  previewCalls: [] as unknown[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn(), useSelector: () => [] }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListTagsQuery: () => ({
    data: [
      { id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] },
      { id: "tag-sub", name: "Sub", path: "CIR", type: "document", item_ids: [] },
    ],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    (arg: { browseDocumentsByTagRequest: { tag_id: string } }) => {
      probe.browseCalls.push(arg.browseDocumentsByTagRequest);
      return { unwrap: () => Promise.resolve({ documents: probe.docs, total: probe.docs.length }) };
    },
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagMutation: () => [
    (arg: { tagCreate: { name: string } }) => {
      probe.createTagCalls.push(arg.tagCreate);
      return { unwrap: () => Promise.resolve({ id: `tag-${arg.tagCreate.name.toLowerCase()}` }) };
    },
  ],
  useDeleteTagMutation: () => [vi.fn()],
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
    preview: (doc: unknown) => probe.previewCalls.push(doc),
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
  DocumentUploadDrawer: (props: Record<string, unknown>) => {
    probe.drawerProps.push(props);
    return null;
  },
}));
vi.mock("@shared/organisms/DocumentViewer/DocumentViewer.tsx", () => ({ DocumentViewer: () => null }));
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({
  InlineDrawer: ({
    layout,
    open,
    onClose,
    children,
  }: {
    layout?: string;
    open?: boolean;
    onClose?: () => void;
    children?: ReactNode;
  }) =>
    layout === "rail" ? (
      <>
        {open && (
          <button onClick={onClose} aria-label="Close tree header">
            Close
          </button>
        )}
        {children}
      </>
    ) : null,
}));

import DocumentWorkspace from "./DocumentWorkspace";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  setCurrentUserPreferences({});
  probe.drawerProps.length = 0;
  probe.canUpdateResources = true;
  probe.createTagCalls.length = 0;
  probe.browseCalls.length = 0;
  probe.docs.length = 0;
  probe.previewCalls.length = 0;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  vi.restoreAllMocks();
});

function folderToggle(name: string): HTMLElement {
  const label = [...container.querySelectorAll<HTMLElement>('[data-row-activation][role="button"]')].find((node) =>
    node.textContent?.includes(name),
  );
  if (!label) throw new Error(`folder row "${name}" not rendered`);
  return label;
}

describe("DocumentWorkspace folder navigation", () => {
  it("starts with the file browser closed and toggles it from the table toolbar", () => {
    const opener = container.querySelector<HTMLButtonElement>('button[aria-label="rework.resources.tree.openPanel"]');
    expect(opener?.getAttribute("aria-expanded")).toBe("false");
    expect(opener?.querySelector(".material-symbols-outlined")?.textContent).toBe("left_panel_open");
    expect(container.querySelector('nav[aria-label="rework.resources.tree.title"]')).toBeNull();
    expect(probe.browseCalls).toHaveLength(0);
    act(() => opener?.click());
    expect(container.querySelector('nav[aria-label="rework.resources.tree.title"]')).toBeTruthy();
    const closer = container.querySelector<HTMLButtonElement>('button[aria-label="rework.resources.tree.closePanel"]');
    expect(closer?.getAttribute("aria-expanded")).toBe("true");
    expect(closer?.querySelector(".material-symbols-outlined")?.textContent).toBe("left_panel_open");
    act(() => closer?.click());
    expect(container.querySelector('nav[aria-label="rework.resources.tree.title"]')).toBeNull();
  });

  it("restores an open file browser from the personal preference", () => {
    act(() => setCurrentUserPreferences({ resources_tree_open: true }));
    expect(container.querySelector('nav[aria-label="rework.resources.tree.title"]')).toBeTruthy();
    expect(
      container.querySelector('button[aria-label="rework.resources.tree.closePanel"]')?.getAttribute("aria-expanded"),
    ).toBe("true");
  });

  it("returns focus to the toolbar opener when the tree header closes", () => {
    act(() => setCurrentUserPreferences({ resources_tree_open: true }));
    const close = container.querySelector<HTMLButtonElement>('button[aria-label="Close tree header"]')!;
    close.focus();
    act(() => close.click());
    const opener = container.querySelector<HTMLButtonElement>('button[aria-label="rework.resources.tree.openPanel"]');
    expect(document.activeElement).toBe(opener);
    expect(container.querySelector('nav[aria-label="rework.resources.tree.title"]')).toBeNull();
  });

  it("opens a folder row's three-dot actions at the right-click position", () => {
    vi.spyOn(document.documentElement, "clientWidth", "get").mockReturnValue(1024);
    vi.spyOn(document.documentElement, "clientHeight", "get").mockReturnValue(768);
    const row = folderToggle("CIR").closest('[class*="datatable-row"]')!;
    expect(row.querySelector('[aria-label="rework.resources.action.more"]')).toBeTruthy();
    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 120, clientY: 80 });
    act(() => row.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true);
    const menu = document.querySelector<HTMLElement>('[role="listbox"]');
    expect(menu?.textContent).toContain("rework.resources.action.rename");
    expect(menu?.textContent).toContain("rework.resources.action.delete");
    expect(menu?.parentElement?.style.left).toBe("120px");
    expect(document.activeElement).toBe(menu);
    expect(row.hasAttribute("data-selected")).toBe(false);
  });

  it("does not reopen a right-click menu after leaving and returning to a folder", async () => {
    const row = folderToggle("CIR").closest('[class*="datatable-row"]')!;
    act(() => row.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    expect(document.querySelector('[role="listbox"]')).toBeTruthy();
    await navigateInto("CIR");
    act(() =>
      (container.querySelector('button[aria-label="rework.resources.action.back"]') as HTMLButtonElement).click(),
    );
    expect(folderToggle("CIR")).toBeTruthy();
    expect(document.querySelector('[role="listbox"]')).toBeNull();
  });

  it("keeps native copy available when right-clicking selected folder text", () => {
    const name = folderToggle("CIR").querySelector('[class*="nameText"]')!;
    const range = document.createRange();
    range.selectNodeContents(name);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    act(() => name.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(false);
    expect(document.querySelector('[role="listbox"]')).toBeNull();
    window.getSelection()?.removeAllRanges();
  });

  it("shows the same file actions on right-click and on the three-dot button", async () => {
    probe.docs.push({
      identity: { document_uid: "uid-1", title: "Report", document_name: "Report.pdf", uploaded_by: null },
      file: { file_type: "pdf", file_size_bytes: 1024 },
      source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
      processing: { stages: { vector: "done" } },
      tags: { tag_ids: ["tag-cir"] },
    });
    await navigateInto("CIR");
    const name = [...container.querySelectorAll('[class*="nameText"]')].find(
      (node) => node.textContent === "Report.pdf",
    )!;
    const row = name.closest('[class*="datatable-row"]')!;
    act(() => row.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    const labels = () => [...document.querySelectorAll('[role="option"]')].map((option) => option.textContent);
    const contextLabels = labels();
    expect(contextLabels.join(" ")).toContain("rework.resources.action.download");
    act(() => document.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })));
    act(() => (row.querySelector('[aria-label="rework.resources.action.more"]') as HTMLButtonElement).click());
    expect(labels()).toEqual(contextLabels);
  });

  it("keeps native copy available when selected text spans two resource names", async () => {
    probe.docs.push({
      identity: { document_uid: "uid-1", title: "Report", document_name: "Report.pdf", uploaded_by: null },
      file: { file_type: "pdf", file_size_bytes: 1024 },
      source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
      processing: { stages: { vector: "done" } },
      tags: { tag_ids: ["tag-cir"] },
    });
    await navigateInto("CIR");
    const folderName = folderToggle("Sub").querySelector('[class*="nameText"]')!;
    const fileName = [...container.querySelectorAll('[class*="nameText"]')].find(
      (node) => node.textContent === "Report.pdf",
    )!;
    const range = document.createRange();
    range.setStart(folderName.firstChild!, 0);
    range.setEnd(fileName.firstChild!, fileName.textContent!.length);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    act(() => folderName.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(false);
    expect(document.querySelector('[role="listbox"]')).toBeNull();
    window.getSelection()?.removeAllRanges();
  });

  it("selects a folder by its name without opening it or highlighting its text", () => {
    const button = folderToggle("CIR");
    const browseCount = probe.browseCalls.length;

    act(() => button.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1 })));

    expect(probe.browseCalls).toHaveLength(browseCount);
    expect(button.closest('[class*="datatable-row"]')?.hasAttribute("data-selected")).toBe(true);
    expect(window.getSelection()?.toString()).toBe("");
  });

  it("clears dragged name text on a click away without changing selected rows", async () => {
    probe.docs.push({
      identity: { document_uid: "uid-1", title: "Report", document_name: "Report.pdf", uploaded_by: null },
      file: { file_type: "pdf", file_size_bytes: 1024 },
      source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
      processing: { stages: { vector: "done" } },
      tags: { tag_ids: ["tag-cir"] },
    });
    await navigateInto("CIR");
    const folder = folderToggle("Sub");
    const name = [...container.querySelectorAll('[class*="nameText"]')].find(
      (node) => node.textContent === "Report.pdf",
    )!;
    const folderRow = folder.closest('[class*="datatable-row"]')!;
    act(() => folder.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1 })));
    expect(folderRow.hasAttribute("data-selected")).toBe(true);

    const range = document.createRange();
    range.selectNodeContents(name);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    expect(window.getSelection()?.toString()).toBe("Report.pdf");
    const blankTableArea = container.querySelector('[class*="datatable-body"]')!;
    blankTableArea.addEventListener("pointerdown", (event) => event.stopPropagation(), { once: true });
    act(() => blankTableArea.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, button: 0 })));
    expect(window.getSelection()?.toString()).toBe("");
    expect(folderRow.hasAttribute("data-selected")).toBe(true);

    window.getSelection()?.addRange(range);
    act(() => blankTableArea.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, button: 2 })));
    expect(window.getSelection()?.toString()).toBe("Report.pdf");
    expect(folderRow.hasAttribute("data-selected")).toBe(true);
    window.getSelection()?.removeAllRanges();
  });

  it("copies folder text dragged from the name cell padding without selecting the row", () => {
    const label = folderToggle("CIR");
    const name = label.querySelector('[class*="nameText"]')!;
    const cell = label.closest("[data-selectable-text]")!;
    expect(label.tagName).toBe("SPAN");
    expect(label.getAttribute("role")).toBe("button");
    const range = document.createRange();
    range.selectNodeContents(name);
    act(() => {
      cell.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: 200, clientY: 10 }));
      name.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 30, clientY: 10 }));
      window.getSelection()?.removeAllRanges();
      window.getSelection()?.addRange(range);
      name.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, clientX: 30, clientY: 10 }));
      name.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1, clientX: 30, clientY: 10 }));
    });
    expect(window.getSelection()?.toString()).toBe("CIR");
    expect(label.closest('[class*="datatable-row"]')?.hasAttribute("data-selected")).toBe(false);
  });

  it("opens a folder on double-click without leaving its name highlighted", async () => {
    const label = folderToggle("CIR");
    const name = label.querySelector('[class*="nameText"]')!;
    const range = document.createRange();
    range.selectNodeContents(name);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    await act(async () => {
      label.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(probe.browseCalls.some((call) => call.tag_id === "tag-cir")).toBe(true);
    expect(window.getSelection()?.toString()).toBe("");
  });

  it("opens a focused folder name with Space", () => {
    const button = folderToggle("CIR");
    act(() => button.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true })));
    expect(probe.browseCalls.some((call) => call.tag_id === "tag-cir")).toBe(true);
  });

  it("opens a folder when its name is activated by assistive technology", () => {
    act(() => folderToggle("CIR").click());
    expect(probe.browseCalls.some((call) => call.tag_id === "tag-cir")).toBe(true);
  });

  it("opens a folder when its row background is double-clicked", async () => {
    const row = folderToggle("CIR").closest('[class*="datatable-row"]');
    if (!row) throw new Error("folder row not rendered");
    const sizeCell = row.querySelectorAll('[class*="datatable-cell"]')[2];
    await act(async () => {
      sizeCell.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(probe.browseCalls.some((call) => call.tag_id === "tag-cir")).toBe(true);
    expect(folderToggle("Sub")).not.toBeNull();
  });

  it("copies file text dragged from the name cell padding without selecting the row", async () => {
    probe.docs.push({
      identity: { document_uid: "uid-1", title: "Report", document_name: "Report.pdf", uploaded_by: null },
      file: { file_type: "pdf", file_size_bytes: 1024 },
      source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
      processing: { stages: { vector: "done" } },
      tags: { tag_ids: ["tag-cir"] },
    });
    await navigateInto("CIR");
    const name = [...container.querySelectorAll('[class*="nameText"]')].find(
      (node) => node.textContent === "Report.pdf",
    )!;
    const cell = name.closest("[data-selectable-text]")!;
    const range = document.createRange();
    range.selectNodeContents(name);
    act(() => {
      cell.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: 200, clientY: 10 }));
      name.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 30, clientY: 10 }));
      window.getSelection()?.removeAllRanges();
      window.getSelection()?.addRange(range);
      name.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, clientX: 30, clientY: 10 }));
      name.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1, clientX: 30, clientY: 10 }));
    });
    expect(window.getSelection()?.toString()).toBe("Report.pdf");
    expect(name.closest('[class*="datatable-row"]')?.hasAttribute("data-selected")).toBe(false);
  });

  it("opens document preview on row double-click after a single click selects it", async () => {
    const doc = {
      identity: { document_uid: "uid-1", title: "Report", document_name: "Report.pdf", uploaded_by: null },
      file: { file_type: "pdf", file_size_bytes: 1024 },
      source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
      processing: { stages: { vector: "done" } },
      tags: { tag_ids: ["tag-cir"] },
    };
    probe.docs.push(doc);
    await navigateInto("CIR");
    const name = [...container.querySelectorAll('[class*="nameText"]')].find(
      (node) => node.textContent === "Report.pdf",
    );
    const row = name?.closest('[class*="datatable-row"]');
    expect(row).not.toBeNull();
    act(() => name?.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1 })));
    expect(row?.hasAttribute("data-selected")).toBe(true);
    expect(probe.previewCalls).toHaveLength(0);
    const range = document.createRange();
    range.selectNodeContents(name!);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    act(() => name?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    expect(probe.previewCalls).toEqual([doc]);
    expect(window.getSelection()?.toString()).toBe("");
  });

  it("Shift-click selects the visible folder and file together in the right-hand table", async () => {
    probe.docs.push({
      identity: { document_uid: "uid-1", title: "Report", document_name: "Report.pdf", uploaded_by: null },
      file: { file_type: "pdf", file_size_bytes: 1024 },
      source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
      processing: { stages: { vector: "done" } },
      tags: { tag_ids: ["tag-cir"] },
    });
    await navigateInto("CIR");
    const folder = folderToggle("Sub").closest('[class*="datatable-row"]')!;
    const file = [...container.querySelectorAll<HTMLElement>('[class*="nameText"]')]
      .find((node) => node.textContent === "Report.pdf")!
      .closest('[class*="datatable-row"]')!;
    act(() => folder.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1 })));
    act(() => file.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1, shiftKey: true })));
    expect(folder.hasAttribute("data-selected")).toBe(true);
    expect(file.hasAttribute("data-selected")).toBe(true);
  });
});

/** Native events carry no dataTransfer in happy-dom; graft the shape React reads.
 * The handler resolves the payload through file-selector's async `fromEvent`, so
 * the drop is awaited past a macrotask for that traversal to settle. */
async function drop(target: HTMLElement, dataTransfer: Record<string, unknown>) {
  await act(async () => {
    const event = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
    target.dispatchEvent(event);
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function dragEnter(target: HTMLElement, dataTransfer: Record<string, unknown>) {
  act(() => {
    const event = new Event("dragenter", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
    target.dispatchEvent(event);
  });
}

function filesTransfer(files: File[]): Record<string, unknown> {
  return { files, types: files.length ? ["Files"] : [] };
}

/** Minimal FileSystemEntry fakes for a directory drop (webkitGetAsEntry API). */
function fakeFileEntry(fullPath: string, file: File) {
  return { isFile: true, isDirectory: false, fullPath, file: (resolve: (f: File) => void) => resolve(file) };
}

function fakeDirEntry(name: string, children: unknown[]) {
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => {
      // Real readers hand out entries in batches and signal the end with an
      // empty batch — file-selector loops until it sees one. It re-invokes
      // readEntries synchronously from inside the callback, so `drained` must
      // flip BEFORE resolving or the loop re-enters forever.
      let drained = false;
      return {
        readEntries: (resolve: (entries: unknown[]) => void) => {
          const batch = drained ? [] : children;
          drained = true;
          resolve(batch);
        },
      };
    },
  };
}

function directoryTransfer(entry: unknown): Record<string, unknown> {
  return { types: ["Files"], files: [], items: [{ kind: "file", webkitGetAsEntry: () => entry }] };
}

function lastDrawerProps(): Record<string, unknown> {
  return probe.drawerProps[probe.drawerProps.length - 1];
}

describe("DocumentWorkspace folder drag-and-drop", () => {
  it("opens the ingestion drawer seeded with the dropped files, targeting the dropped-on folder", async () => {
    const files = [new File(["a"], "a.pdf"), new File(["b"], "b.docx")];
    await drop(folderToggle("CIR"), filesTransfer(files));

    const props = lastDrawerProps();
    expect(props.isOpen).toBe(true);
    expect((props.initialFiles as File[]).map((f) => f.name)).toEqual(["a.pdf", "b.docx"]);
    expect(props.destinationPath).toBe("CIR");
    expect((props.metadata as { tags: string[] }).tags).toEqual(["tag-cir"]);
  });

  it("expands a dropped directory into all its files, recursively and flat", async () => {
    const dir = fakeDirEntry("batch", [
      fakeFileEntry("/batch/a.pdf", new File(["a"], "a.pdf")),
      fakeDirEntry("sub", [fakeFileEntry("/batch/sub/b.docx", new File(["b"], "b.docx"))]),
    ]);
    await drop(folderToggle("CIR"), directoryTransfer(dir));

    const props = lastDrawerProps();
    expect(props.isOpen).toBe(true);
    expect((props.initialFiles as File[]).map((f) => f.name).sort((a, b) => a.localeCompare(b))).toEqual([
      "a.pdf",
      "b.docx",
    ]);
  });

  it("uses the same folder drop target and hover outline in the tree", async () => {
    act(() => {
      container.querySelector<HTMLButtonElement>('button[aria-label="rework.resources.tree.openPanel"]')?.click();
    });
    const name = container.querySelector<HTMLButtonElement>(
      'nav[aria-label="rework.resources.tree.title"] button[title="CIR"]',
    );
    const row = name?.parentElement;
    if (!row) throw new Error("tree folder not rendered");
    const tableRow = folderToggle("CIR").closest('[class*="datatable-row"]')!;
    const transfer = filesTransfer([new File(["a"], "a.pdf")]);

    dragEnter(row, transfer);
    expect(row.hasAttribute("data-drag-over")).toBe(true);
    expect(tableRow.querySelector('[data-drag-over="true"]')).toBeNull();
    dragEnter(tableRow.querySelector<HTMLElement>("[data-row-activation]")!, transfer);
    expect(row.hasAttribute("data-drag-over")).toBe(false);
    expect(tableRow.querySelector('[data-drag-over="true"]')).not.toBeNull();
    dragEnter(row, transfer);
    await drop(row, transfer);

    expect(lastDrawerProps().destinationPath).toBe("CIR");
    expect(row.hasAttribute("data-drag-over")).toBe(false);
  });

  it("ignores a drop that carries no files (e.g. dragged text)", async () => {
    await drop(folderToggle("CIR"), filesTransfer([]));

    expect(lastDrawerProps().isOpen).toBe(false);
  });

  it("does not react to drops without CAN_UPDATE_RESOURCES (same gate as the upload action)", async () => {
    probe.canUpdateResources = false;
    act(() => {
      root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
    });

    await drop(folderToggle("CIR"), filesTransfer([new File(["a"], "a.pdf")]));

    expect(lastDrawerProps().isOpen).toBe(false);
  });

  it("clears the seeded files when the drawer closes, so a later plain open starts empty", async () => {
    await drop(folderToggle("CIR"), filesTransfer([new File(["a"], "a.pdf")]));
    act(() => {
      (lastDrawerProps().onClose as () => void)();
    });

    const props = lastDrawerProps();
    expect(props.isOpen).toBe(false);
    expect(props.initialFiles).toBeUndefined();
  });
});

async function navigateInto(name: string) {
  await act(async () => {
    folderToggle(name).dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    // flush the entry effect's browse promise so perTag settles inside act
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("DocumentWorkspace full-page drop (one folder per page)", () => {
  it("rejects loose files dropped at the corpus root — only folders can land there", async () => {
    await drop(container.firstElementChild as HTMLElement, filesTransfer([new File(["a"], "a.pdf")]));

    expect(lastDrawerProps().isOpen).toBe(false);
  });

  it("accepts a folder dropped at the corpus root, keeping its structure", async () => {
    const dir = fakeDirEntry("batch", [
      fakeFileEntry("/batch/a.pdf", new File(["a"], "a.pdf")),
      fakeDirEntry("sub", [fakeFileEntry("/batch/sub/b.docx", new File(["b"], "b.docx"))]),
    ]);
    await drop(container.firstElementChild as HTMLElement, directoryTransfer(dir));

    const props = lastDrawerProps();
    expect(props.isOpen).toBe(true);
    expect(props.destinationPath).toBeUndefined();
    expect((props.metadata as { tags: string[] }).tags).toEqual([]);
    expect(typeof props.ensureFolderPath).toBe("function");
    expect(props.requireFolderPerFile).toBe(true);
    expect((props.initialFiles as File[]).map((f) => f.name).sort((a, b) => a.localeCompare(b))).toEqual([
      "a.pdf",
      "b.docx",
    ]);
  });

  it("dropping anywhere inside an open folder opens the drawer targeting that folder", async () => {
    await navigateInto("CIR");
    await drop(container.firstElementChild as HTMLElement, filesTransfer([new File(["a"], "a.pdf")]));

    const props = lastDrawerProps();
    expect(props.isOpen).toBe(true);
    expect(props.destinationPath).toBe("CIR");
    expect((props.metadata as { tags: string[] }).tags).toEqual(["tag-cir"]);
  });

  it("a drop on a subfolder row targets that subfolder, not the page's open folder", async () => {
    await navigateInto("CIR");
    await drop(folderToggle("Sub"), filesTransfer([new File(["a"], "a.pdf")]));

    expect(lastDrawerProps().destinationPath).toBe("CIR/Sub");
  });

  it("clears the page drop overlay after a file is dropped on a subfolder row", async () => {
    await navigateInto("CIR");
    const workspace = container.firstElementChild as HTMLElement;
    const row = folderToggle("Sub");
    const transfer = filesTransfer([new File(["a"], "a.pdf")]);

    dragEnter(workspace, transfer);
    expect(workspace.getAttribute("data-page-drag-over")).toBe("true");

    dragEnter(row, transfer);
    await drop(row, transfer);

    expect(lastDrawerProps().destinationPath).toBe("CIR/Sub");
    expect(workspace.hasAttribute("data-page-drag-over")).toBe(false);
  });
});

describe("DocumentWorkspace folder page reload on entry", () => {
  it("reloads the folder's document page on every entry, not just the first", async () => {
    await navigateInto("CIR");
    const backButton = [...container.querySelectorAll("button")].find((b) =>
      b.getAttribute("aria-label")?.includes("rework.resources.action.back"),
    );
    if (!backButton) throw new Error("back button not rendered");
    await act(async () => {
      backButton.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await navigateInto("CIR");

    // One browse per entry: a folder first opened while its files were still
    // uploading must not stay frozen on that first empty snapshot.
    expect(probe.browseCalls.filter((call) => call.tag_id === "tag-cir")).toHaveLength(2);
  });
});

describe("DocumentWorkspace nested tag creation (ensureFolderPath)", () => {
  async function ensureAfterDropOnCir(segments: string[]): Promise<string | null> {
    await drop(folderToggle("CIR"), filesTransfer([new File(["a"], "a.pdf")]));
    const ensure = lastDrawerProps().ensureFolderPath as (segments: string[]) => Promise<string | null>;
    let leaf: string | null = null;
    await act(async () => {
      leaf = await ensure(segments);
    });
    return leaf;
  }

  it("creates one document tag per missing level under the drop target and returns the leaf's id", async () => {
    const leaf = await ensureAfterDropOnCir(["Alpha", "Beta"]);

    expect(probe.createTagCalls).toEqual([
      { name: "Alpha", path: "CIR", type: "document", team_id: "team-1" },
      { name: "Beta", path: "CIR/Alpha", type: "document", team_id: "team-1" },
    ]);
    expect(leaf).toBe("tag-beta");
  });

  it("reuses an already-materialized folder instead of re-creating its tag", async () => {
    const leaf = await ensureAfterDropOnCir(["Sub"]);

    expect(probe.createTagCalls).toEqual([]);
    expect(leaf).toBe("tag-sub");
  });
});

describe("DocumentWorkspace stats refresh", () => {
  it("notifies onDocumentsChanged when the upload drawer completes", () => {
    const onDocumentsChanged = vi.fn();
    act(() => {
      root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} onDocumentsChanged={onDocumentsChanged} />);
    });

    act(() => {
      (lastDrawerProps().onUploadComplete as () => void)();
    });

    expect(onDocumentsChanged).toHaveBeenCalled();
  });
});
