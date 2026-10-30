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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  findEntries: vi.fn(),
  createConflict: false,
  refetch: vi.fn(),
  queryOptions: {} as Record<string, unknown>,
  processingEnabled: false,
  processing: {} as Record<string, import("../../../../../slices/controlPlane/controlPlaneOpenApi").Summary>,
  uploaders: {} as Record<string, string>,
  inclusion: vi.fn().mockResolvedValue({}),
  starts: vi.fn().mockResolvedValue({}),
  documents: [] as import("../../../../../slices/controlPlane/controlPlaneOpenApi").Document[],
  drawerProps: [] as Record<string, unknown>[],
  folders: [] as {
    id: string;
    name: string;
    parent_id: string | null;
    space_id: string;
    path: string;
    created_at: string;
  }[],
  query: {} as Record<string, unknown>,
  canWrite: true,
  error: false,
  fetching: false,
  creates: [] as Record<string, unknown>[],
  deletes: [] as string[],
  deleteDocument: vi.fn().mockResolvedValue({}),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  renames: [] as Record<string, unknown>[],
  deferDelete: false,
  deleteResolves: [] as (() => void)[],
  createResolve: undefined as (() => void) | undefined,
  confirm: undefined as undefined | { message: string; onConfirm: () => Promise<void> },
  legacyRequests: [] as string[],
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useSetRetrievableMutation: () => [(args: unknown) => ({ unwrap: () => probe.inclusion(args) })],
  useLazyEntriesQuery: () => [(args: unknown) => ({ unwrap: () => probe.findEntries(args) })],
  useEntriesQuery: (query: Record<string, unknown>, options: Record<string, unknown>) => {
    probe.queryOptions = options;
    probe.query = query;
    const parent = query.parentId as string | undefined;
    const ancestors = [];
    let node = probe.folders.find((f) => f.id === parent);
    while (node) {
      ancestors.unshift(node);
      node = probe.folders.find((f) => f.id === node!.parent_id);
    }
    const matches = probe.folders.filter(
      (f) => f.parent_id === (parent ?? null) && f.name.toLowerCase().includes(String(query.search).toLowerCase()),
    );
    const items = [
      ...matches.map((data) => ({ kind: "folder", data })),
      ...probe.documents.filter((d) => d.folder_id === parent).map((data) => ({ kind: "document", data })),
    ];
    return {
      currentData: {
        items: items.slice(Number(query.offset), Number(query.offset) + Number(query.limit)),
        ancestors,
        total: items.length,
        offset: query.offset,
        limit: query.limit,
        can_write: probe.canWrite,
        processing_enabled: probe.processingEnabled,
        processing: probe.processing,
        uploaders: probe.uploaders,
      },
      isSuccess: !probe.error,
      isError: probe.error,
      isFetching: probe.fetching,
      refetch: probe.refetch,
    };
  },
  useCreateFolderMutation: () => [
    (args: { createFolder: Record<string, unknown> }) => ({
      unwrap: () => {
        probe.creates.push(args.createFolder);
        if (probe.createConflict) return Promise.reject({ status: 409 });
        return new Promise<void>((resolve) => {
          probe.createResolve = resolve;
        });
      },
    }),
  ],
  useRenameFolderMutation: () => [
    (args: { id: string; rename: { name: string } }) => ({
      unwrap: async () => {
        probe.renames.push(args);
        probe.folders.find((f) => f.id === args.id)!.name = args.rename.name;
      },
    }),
  ],
  useDeleteDocumentMutation: () => [(args: unknown) => ({ unwrap: () => probe.deleteDocument(args) })],
  useDeleteFolderMutation: () => [
    (args: { id: string }) => ({
      unwrap: () => {
        probe.deletes.push(args.id);
        return probe.deferDelete
          ? new Promise<void>((resolve) => probe.deleteResolves.push(resolve))
          : Promise.resolve();
      },
    }),
  ],
}));
vi.mock("../../../../features/imports/managerImportRun", () => ({
  startManagerProcessing: (...args: unknown[]) => probe.starts(...args),
  managerActor: () => "writer",
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn(), useSelector: () => [] }));
vi.mock("../../../../../slices/legacyKnowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListTagsQuery: (_args: unknown, options: { skip: boolean }) => {
    if (!options.skip) probe.legacyRequests.push("tags");
    return { data: undefined, isLoading: false, refetch: vi.fn() };
  },
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    (_arg: unknown) => {
      probe.legacyRequests.push("browse");
      return { unwrap: async () => ({ documents: [], total: 0 }) };
    },
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [() => probe.legacyRequests.push("sizes")],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [() => probe.legacyRequests.push("process")],
  useCreateTagMutation: () => [() => probe.legacyRequests.push("createTag"), {}],
  useDeleteTagMutation: () => [() => probe.legacyRequests.push("deleteTag")],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({}) })),
  ],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [], selectAllTasks: () => [] }));
vi.mock("../../../../features/tasks/useRefetchOnTaskSettled", () => ({ useRefetchOnTaskSettled: () => {} }));
vi.mock("../../../../features/tasks/useNotifyOnNewTaskTarget", () => ({ useNotifyOnNewTaskTarget: () => {} }));
vi.mock("../../../../../components/documents/common/useDocumentCommands", () => ({
  useDocumentCommands: ({ setRetrievable }: { setRetrievable: (doc: any, value: boolean) => Promise<unknown> }) => ({
    previewTarget: null,
    closePreview: () => {},
    preview: () => {},
    download: async () => {},
    toggleRetrievable: async (doc: any) => {
      await setRetrievable(doc, !doc.source.retrievable);
      return !doc.source.retrievable;
    },
    removeFromLibrary: async () => {},
  }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({
    showConfirmationDialog: (value: typeof probe.confirm) => {
      probe.confirm = value;
    },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: probe.showSuccess, showError: probe.showError }),
}));
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: { id: "team-1" } }),
  useUsersByIdsQuery: () => ({ data: [] }),
}));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canUpdateResources: false }),
}));
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
const view = (space = "space-1") => (
  <DocumentWorkspace key={space} teamId={space} managerSpaceId={space} isPersonalTeam={false} />
);
const render = async (space = "space-1") => {
  await act(async () => {
    root.render(view(space));
  });
};
const click = async (element: Element | null) => {
  expect(element).toBeTruthy();
  await act(async () => {
    element!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
};
const namedButton = (name: string) =>
  [...container.querySelectorAll("button")].find((b) => b.textContent?.endsWith(name))!;
const action = (name: string) => container.querySelector(`button[aria-label="rework.resources.${name}"]`);
function setName(name: string) {
  const input = document.querySelector('[role="dialog"] input') as HTMLInputElement;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, name);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function menuAction(name: string) {
  await click(action("action.more"));
  await click(
    [
      ...document.querySelectorAll(
        '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
      ),
    ].find((b) => b.textContent?.includes(`rework.resources.action.${name}`))!,
  );
}
beforeEach(async () => {
  probe.documents = [];
  probe.deleteDocument.mockReset().mockResolvedValue({});
  probe.showSuccess.mockClear();
  probe.showError.mockClear();
  probe.refetch.mockClear();
  probe.inclusion.mockClear();
  probe.findEntries.mockReset();
  probe.createConflict = false;
  probe.processingEnabled = false;
  probe.processing = {};
  probe.uploaders = {};
  probe.starts.mockClear();
  probe.folders = [
    {
      id: "root-id",
      name: "Library",
      parent_id: null,
      space_id: "space-1",
      path: "/root-id/",
      created_at: "2026-10-18T08:00:00Z",
    },
    {
      id: "child-id",
      name: "Child",
      parent_id: "root-id",
      space_id: "space-1",
      path: "/root-id/child-id/",
      created_at: "2026-10-18T08:00:01Z",
    },
  ];
  probe.canWrite = true;
  probe.error = false;
  probe.fetching = false;
  probe.creates = [];
  probe.renames = [];
  probe.deletes = [];
  probe.legacyRequests = [];
  probe.drawerProps = [];
  probe.confirm = undefined;
  probe.createResolve = undefined;
  probe.deferDelete = false;
  probe.deleteResolves = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await render();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  act(() => root.unmount());
  container.remove();
  document.querySelectorAll('[role="presentation"]').forEach((el) => el.remove());
});

it("restores both original controls from manager authority, navigates by id and keeps uploads outside KF", async () => {
  expect(action("menu.newFolder")).not.toBeNull();
  expect(action("action.addFile")).not.toBeNull();
  expect((action("action.addFile") as HTMLButtonElement).disabled).toBe(true);
  await click(namedButton("Library"));
  expect(probe.query.parentId).toBe("root-id");
  expect(namedButton("Child")).toBeDefined();
  await click(action("action.addFile"));
  const drawer = probe.drawerProps[probe.drawerProps.length - 1]!;
  expect(drawer.isOpen).toBe(true);
  expect(drawer.managerDestination).toEqual({ spaceId: "space-1", folderId: "root-id", processingEnabled: false });
  expect(drawer.unavailableReason).toBeUndefined();
  expect(drawer.metadata).toEqual({ tags: [] });
  expect(drawer.ensureFolderPath).toBeTypeOf("function");
  expect(probe.legacyRequests).toEqual([]);
});

it("uses the existing create modal, sends the owning space/parent once and ignores completion after navigation", async () => {
  await click(namedButton("Library"));
  await click(action("menu.newFolder"));
  setName("Nested");
  const create = [...document.querySelectorAll('[role="dialog"] button')].find((b) =>
    b.textContent?.includes("folderModal.create"),
  )!;
  await click(create);
  await click(create);
  expect(probe.creates).toEqual([{ space_id: "space-1", parent_id: "root-id", name: "Nested" }]);
  await render("space-2");
  await act(async () => {
    probe.createResolve!();
  });
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(probe.query.id).toBe("space-2");
  expect(probe.query.parentId).toBeUndefined();
  expect(probe.legacyRequests).toEqual([]);
});

it("renames through the original modal without rewriting descendants", async () => {
  await menuAction("rename");
  setName("Renamed");
  await click(
    [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.includes("renameModal.save"))!,
  );
  expect(probe.renames).toEqual([{ id: "root-id", rename: { name: "Renamed" } }]);
  await click(namedButton("Renamed"));
  expect(probe.query.parentId).toBe("root-id");
  expect(namedButton("Child")).toBeDefined();
  expect(probe.legacyRequests).toEqual([]);
});

it("confirms subtree deletion without enumerating documents and discards a stale confirmation", async () => {
  await menuAction("delete");
  expect(probe.confirm?.message).toContain("deleteManagerFolder");
  await act(async () => {
    await probe.confirm!.onConfirm();
  });
  expect(probe.deletes).toEqual(["root-id"]);
  await render("space-2");
  await act(async () => {
    await probe.confirm!.onConfirm();
  });
  expect(probe.deletes).toEqual(["root-id"]);
  expect(probe.legacyRequests).toEqual([]);
});

it("withholds old write authority during error/retry and restores only a fresh decision", async () => {
  probe.error = true;
  await render();
  expect(action("menu.newFolder")).toBeNull();
  probe.error = false;
  probe.fetching = true;
  await render();
  expect(action("menu.newFolder")).toBeNull();
  probe.fetching = false;
  probe.canWrite = false;
  await render();
  expect(action("menu.newFolder")).toBeNull();
  probe.canWrite = true;
  await render();
  expect(action("menu.newFolder")).not.toBeNull();
});

it("returns to a valid page when deletion empties the last page", async () => {
  const template = probe.folders[0];
  probe.folders = Array.from({ length: 51 }, (_, i) => ({ ...template, id: `folder-${i}`, name: `Folder ${i}` }));
  await render();
  await click(container.querySelector('button[aria-label="dataTable.pagination.next"]'));
  expect(probe.query.offset).toBe(50);
  probe.folders.pop();
  await render();
  expect(probe.query.offset).toBe(0);
  expect(namedButton("Folder 0")).toBeDefined();
});

it("shares one pending deletion between repeated unit and bulk confirmations", async () => {
  probe.deferDelete = true;
  await menuAction("delete");
  let pending!: Promise<void>;
  await act(async () => {
    pending = probe.confirm!.onConfirm();
  });
  await menuAction("delete");
  await act(async () => {
    await probe.confirm!.onConfirm();
  });
  await act(async () => {
    (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click();
  });
  await click(action("bulkActions.delete"));
  let bulk!: Promise<void>;
  await act(async () => {
    bulk = probe.confirm!.onConfirm();
  });
  expect(probe.deletes).toEqual(["root-id"]);
  await act(async () => {
    probe.deleteResolves[0]();
    await Promise.all([pending, bulk]);
  });
});

it("releases bulk busy state even after navigating during deletion", async () => {
  probe.deferDelete = true;
  await act(async () => {
    (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click();
  });
  await click(action("bulkActions.delete"));
  let pending!: Promise<void>;
  await act(async () => {
    pending = probe.confirm!.onConfirm();
  });
  await click(namedButton("Library"));
  await act(async () => {
    probe.deleteResolves[0]();
    await pending;
  });
  await act(async () => {
    (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click();
  });
  expect((action("bulkActions.delete") as HTMLButtonElement).disabled).toBe(false);
});

it("keeps a root-row file drop targeted at that folder in the original upload panel", async () => {
  const file = new File(["a"], "report.pdf");
  const event = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", { value: { files: [file], types: ["Files"] } });
  await act(async () => {
    namedButton("Library").dispatchEvent(event);
  });
  const drawer = probe.drawerProps[probe.drawerProps.length - 1]!;
  expect(drawer.isOpen).toBe(true);
  expect(drawer.initialFiles).toEqual([file]);
  expect(drawer.requireFolderPerFile).toBe(false);
  expect(drawer.destinationPath).toBe("Library");
  expect(drawer.managerDestination).toEqual({ spaceId: "space-1", folderId: "root-id", processingEnabled: false });
  expect(drawer.unavailableReason).toBeUndefined();
  expect(probe.legacyRequests).toEqual([]);
});

it("shows the uploader name the manager listing resolved, and the subject otherwise", async () => {
  probe.folders = probe.folders.filter((f) => !f.parent_id);
  const document = (id: string, created_by: string) => ({
    id,
    retrievable: true,
    retrievable_pending: false,
    space_id: "space-1",
    folder_id: "root-id",
    name: `${id}.txt`,
    mime: "text/plain",
    size: 5,
    sha256: "a".repeat(64),
    created_by,
    created_at: "2026-10-19T08:00:00Z",
  });
  probe.documents = [document("named", "writer"), document("unknown", "ghost")];
  probe.uploaders = { writer: "Priya Nair" };
  await render();
  await click(namedButton("Library"));
  expect(container.textContent).toContain("Priya Nair");
  expect(container.textContent).not.toContain("writer");
  expect(container.textContent).toContain("ghost");
  expect(probe.legacyRequests).toEqual([]);
});

it("keeps document bulk deletion available while ZIP and search remain unavailable", async () => {
  probe.folders = probe.folders.filter((f) => !f.parent_id);
  probe.documents = [
    {
      id: "document",
      retrievable: false,
      retrievable_pending: false,
      space_id: "space-1",
      folder_id: "root-id",
      name: "original.txt",
      mime: "text/plain",
      size: 5,
      sha256: "a".repeat(64),
      created_by: "writer",
      created_at: "2026-10-19T08:00:00Z",
    },
  ];
  await render();
  await click(namedButton("Library"));
  await act(async () => {
    (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click();
  });
  expect(container.textContent).toContain("rework.documentStorage.stored");
  expect(container.querySelector('[data-variant="pending"]')).toBeNull();
  // The registry alone determines this state, including a newly mounted page.
  await act(async () => {
    root.unmount();
  });
  root = createRoot(container);
  await render();
  await click(namedButton("Library"));
  expect(container.textContent).toContain("rework.documentStorage.stored");
  await act(async () => {
    (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click();
  });
  for (const name of ["download", "includeInSearch"]) {
    const button = action(`bulkActions.${name}`) as HTMLButtonElement;
    expect(button).not.toBeNull();
    expect(button.disabled).toBe(true);
    await act(async () => button.click());
  }
  expect(probe.deletes).toEqual([]);
  expect(probe.confirm).toBeUndefined();
  expect((action("bulkActions.delete") as HTMLButtonElement).disabled).toBe(false);
  expect(probe.legacyRequests).toEqual([]);
});

it.each(["row", "bulk"])(
  "starts a stored manager document through the %s control with no legacy tag",
  async (entry) => {
    probe.processingEnabled = true;
    probe.folders = probe.folders.slice(0, 1);
    probe.documents = [
      {
        id: "doc",
        retrievable: false,
        retrievable_pending: false,
        space_id: "space-1",
        folder_id: "root-id",
        name: "stored.txt",
        size: 5,
        mime: "text/plain",
        sha256: "a".repeat(64),
        created_by: "writer",
        created_at: "2026-10-19T08:00:00Z",
      },
    ];
    await render();
    await click(namedButton("Library"));
    if (entry === "row") await menuAction("relaunchIngestion");
    else {
      await act(async () => (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click());
      await click(container.querySelector('button[aria-label^="rework.resources.bulkActions.relaunchIngestion"]'));
    }
    const dialog = document.querySelector('[role="dialog"]')!;
    expect(dialog).not.toBeNull();
    await click(dialog.querySelector('button[aria-haspopup="listbox"]'));
    await click(
      [...document.querySelectorAll('[role="presentation"] li')].find((node) =>
        node.textContent?.includes("documentLibrary.profileMedium"),
      )!,
    );
    await click(
      [...dialog.querySelectorAll("button")].find(
        (button) => button.textContent === "rework.resources.action.relaunchIngestion",
      )!,
    );
    expect(probe.starts).toHaveBeenCalledWith(expect.any(Function), "doc", "medium", undefined);
    expect(probe.legacyRequests).toEqual([]);
  },
);

it("refreshes on focus and polls only active processing in the current directory", async () => {
  vi.useFakeTimers();
  expect(probe.queryOptions.pollingInterval ?? 0).toBe(0);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(6000);
  });
  expect(probe.refetch).not.toHaveBeenCalled();
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  expect(probe.refetch).toHaveBeenCalledTimes(1);
  probe.refetch.mockClear();
  // Only status is consumed by this polling fixture; no document row is rendered.
  probe.processing = { doc: { status: "running" } as (typeof probe.processing)[string] };
  await render();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(probe.refetch).toHaveBeenCalledTimes(1);
  probe.processing = { doc: { status: "succeeded" } as (typeof probe.processing)[string] };
  await render();
  probe.refetch.mockClear();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(6000);
  });
  expect(probe.refetch).not.toHaveBeenCalled();
});

it("finds an existing upload folder in mixed entry pages after a create conflict", async () => {
  await click(namedButton("Library"));
  await click(action("action.addFile"));
  const drawer = probe.drawerProps[probe.drawerProps.length - 1]!;
  probe.createConflict = true;
  probe.findEntries
    .mockResolvedValueOnce({ items: [{ kind: "document", data: { id: "wrong", name: "Nested" } }], total: 2 })
    .mockResolvedValueOnce({ items: [{ kind: "folder", data: { id: "existing", name: "Nested" } }], total: 2 });
  const ensure = drawer.ensureFolderPath as (segments: string[]) => Promise<string | null>;
  expect(await ensure(["Nested"])).toBe("existing");
  expect(probe.findEntries.mock.calls.map(([args]) => args.offset)).toEqual([0, 1]);
  expect(probe.findEntries.mock.calls[0][0]).toMatchObject({ id: "space-1", parentId: "root-id", search: "Nested" });
});

it("recovers an upload folder by its canonical name after a create conflict", async () => {
  await click(namedButton("Library"));
  await click(action("action.addFile"));
  const drawer = probe.drawerProps[probe.drawerProps.length - 1]!;
  probe.createConflict = true;
  probe.findEntries.mockResolvedValueOnce({
    items: [{ kind: "folder", data: { id: "existing", name: "\u00c9t\u00e9" } }],
    total: 1,
  });
  const ensure = drawer.ensureFolderPath as (segments: string[]) => Promise<string | null>;
  expect(await ensure([" E\u0301te\u0301 "])).toBe("existing");
  expect(probe.creates[probe.creates.length - 1]).toMatchObject({ name: "\u00c9t\u00e9" });
  expect(probe.findEntries.mock.calls[0][0]).toMatchObject({ search: "\u00c9t\u00e9" });
});

it("pauses active directory refresh while hidden and refreshes on focus", async () => {
  vi.useFakeTimers();
  const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  probe.processing = { doc: { status: "pending" } as (typeof probe.processing)[string] };
  await render();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(6000);
  });
  expect(probe.refetch).not.toHaveBeenCalled();
  visibility.mockReturnValue("visible");
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  expect(probe.refetch).toHaveBeenCalledTimes(1);
  await render();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(probe.refetch).toHaveBeenCalledTimes(2);
});

it.each([true, false])("routes the unchanged inclusion menu to manager for inclusion=%s", async (retrievable) => {
  probe.folders = probe.folders.slice(0, 1);
  probe.documents = [
    {
      id: "doc",
      space_id: "space-1",
      folder_id: "root-id",
      name: "report.pdf",
      mime: "application/pdf",
      size: 42,
      sha256: "a".repeat(64),
      created_at: "2026-10-23",
      created_by: "writer",
      retrievable,
      retrievable_pending: false,
    },
  ];
  await render();
  await click(namedButton("Library"));
  await menuAction(retrievable ? "searchable" : "includeInSearch");
  expect(probe.inclusion).toHaveBeenCalledWith({ id: "doc", setRetrievable: { retrievable: !retrievable } });
});

async function openDocuments(count = 1) {
  probe.folders = probe.folders.slice(0, 1);
  probe.documents = Array.from({ length: count }, (_, index) => ({
    id: `doc-${index}`,
    space_id: "space-1",
    folder_id: "root-id",
    name: `report-${index}.pdf`,
    mime: "application/pdf",
    size: 42,
    sha256: "a".repeat(64),
    created_at: "2026-10-24",
    created_by: "writer",
    retrievable: false,
    retrievable_pending: false,
  }));
  await render();
  await click(namedButton("Library"));
}

it("confirms manager document deletion and reports success without using legacy tags", async () => {
  await openDocuments();
  await menuAction("delete");
  expect(probe.confirm?.message).toBe("rework.resources.confirm.deleteManagerDocument");
  expect(probe.deleteDocument).not.toHaveBeenCalled();
  await act(async () => {
    await probe.confirm!.onConfirm();
  });
  expect(probe.deleteDocument).toHaveBeenCalledExactlyOnceWith({ id: "doc-0" });
  expect(probe.showSuccess).toHaveBeenCalledWith({ summary: "documentLibrary.removeSuccess" });
  expect(probe.legacyRequests).toEqual([]);
});

it.each(["pending", "running"] as const)(
  "disables manager document deletion while processing is %s",
  async (status) => {
    probe.processing = {
      "doc-0": {
        id: "processing",
        document_id: "doc-0",
        status,
        stage: "extraction",
        profile: "fast",
        revision: 1,
        created_at: "2026-10-24T10:00:00Z",
        chunks: 0,
        vectors: 0,
      },
    };
    await openDocuments();
    await click(action("action.more"));
    const item = [...document.querySelectorAll('[role="presentation"] li')].find((node) =>
      node.textContent?.includes("rework.resources.action.delete"),
    )!;
    expect(item.getAttribute("aria-disabled")).toBe("true");
    expect(item.textContent).toContain("rework.resources.action.deleteDisabledWhileProcessing");
    await click(item);
    expect(probe.confirm).toBeUndefined();
    expect(probe.deleteDocument).not.toHaveBeenCalled();
  },
);

it("attempts every selected manager document and reports a processing conflict as a partial failure", async () => {
  probe.deleteDocument
    .mockResolvedValueOnce({})
    .mockRejectedValueOnce({ status: 409, data: { detail: "processing_active" } });
  await openDocuments(2);
  await act(async () => {
    (container.querySelectorAll('input[type="checkbox"]')[0] as HTMLInputElement).click();
  });
  await click(action("bulkActions.delete"));
  expect(probe.confirm?.message).toBe("rework.resources.confirm.deleteManagerDocuments");
  await act(async () => {
    await probe.confirm!.onConfirm();
  });
  expect(probe.deleteDocument.mock.calls).toEqual([[{ id: "doc-0" }], [{ id: "doc-1" }]]);
  expect(probe.showError).toHaveBeenCalledWith({
    summary: "validation.error",
    detail: "rework.resources.confirm.deleteManagerPartial",
  });
  expect(probe.showSuccess).not.toHaveBeenCalled();
});

it("shows the backend detail when a manager document deletion fails", async () => {
  probe.deleteDocument.mockRejectedValueOnce({ status: 409, data: { detail: "processing_active" } });
  await openDocuments();
  await menuAction("delete");
  await act(async () => {
    await probe.confirm!.onConfirm();
  });
  expect(probe.showError).toHaveBeenCalledWith({ summary: "validation.error", detail: "processing_active" });
});
