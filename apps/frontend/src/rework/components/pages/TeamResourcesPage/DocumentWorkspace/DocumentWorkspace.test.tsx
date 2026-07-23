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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  drawerProps: [] as Record<string, unknown>[],
  canUpdateResources: true,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [] }));
vi.mock("../../../../features/tasks/useRefetchOnTaskSuccess", () => ({ useRefetchOnTaskSuccess: () => {} }));
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
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({ InlineDrawer: () => null }));

import DocumentWorkspace from "./DocumentWorkspace";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  probe.drawerProps.length = 0;
  probe.canUpdateResources = true;
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
});

function folderToggle(name: string): HTMLButtonElement {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
  if (!button) throw new Error(`folder row "${name}" not rendered`);
  return button;
}

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

  it("targets the folder when the drop lands on its expanded contents, not the row itself", async () => {
    await act(async () => {
      folderToggle("CIR").click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const hint = [...container.querySelectorAll("div")].find((d) => d.textContent === "rework.resources.empty.folder");
    if (!hint) throw new Error("expanded empty-folder hint not rendered");

    await drop(hint, filesTransfer([new File(["a"], "a.pdf")]));

    const props = lastDrawerProps();
    expect(props.isOpen).toBe(true);
    expect(props.destinationPath).toBe("CIR");
    expect((props.metadata as { tags: string[] }).tags).toEqual(["tag-cir"]);
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
