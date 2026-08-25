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
  createTagCalls: [] as Record<string, unknown>[],
  browseCalls: [] as { tag_id: string }[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
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
      return { unwrap: () => Promise.resolve({ documents: [], total: 0 }) };
    },
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [
    (arg: { tagCreate: { name: string } }) => {
      probe.createTagCalls.push(arg.tagCreate);
      return { unwrap: () => Promise.resolve({ id: `tag-${arg.tagCreate.name.toLowerCase()}` }) };
    },
  ],
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
  probe.createTagCalls.length = 0;
  probe.browseCalls.length = 0;
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

  // FRONT-09.G replaced the always-expanded tree with breadcrumb drill-down: a
  // folder's children are only visible after navigating INTO it (a full view
  // swap), not nested under its row — so "drop lands on expanded contents
  // distinct from the row" no longer has an equivalent. Dropping directly on
  // a folder row (covered above) is the one drop surface in the new model.

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
    folderToggle(name).click();
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
