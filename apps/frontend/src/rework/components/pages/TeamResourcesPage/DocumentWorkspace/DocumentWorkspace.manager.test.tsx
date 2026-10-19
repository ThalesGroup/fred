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
  documents: [] as import("../../../../../slices/fredManager/fredManagerOpenApi").Document[],
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
  renames: [] as Record<string, unknown>[],
  deferDelete: false,
  deleteResolves: [] as (() => void)[],
  createResolve: undefined as (() => void) | undefined,
  confirm: undefined as undefined | { message: string; onConfirm: () => Promise<void> },
  legacyRequests: [] as string[],
}));
vi.mock("../../../../../slices/fredManager/fredManagerApiEnhancements", () => ({
  useLazyListFoldersQuery: () => [vi.fn()],
  useEntriesQuery: (query: Record<string, unknown>) => {
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
      },
      isSuccess: !probe.error,
      isError: probe.error,
      isFetching: probe.fetching,
      refetch: vi.fn(),
    };
  },
  useCreateFolderMutation: () => [
    (args: { createFolder: Record<string, unknown> }) => ({
      unwrap: () => {
        probe.creates.push(args.createFolder);
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
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn(), useSelector: () => [] }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
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
  useConfirmationDialog: () => ({
    showConfirmationDialog: (value: typeof probe.confirm) => {
      probe.confirm = value;
    },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
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
  expect(drawer.managerDestination).toEqual({ spaceId: "space-1", folderId: "root-id" });
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
  expect(drawer.managerDestination).toEqual({ spaceId: "space-1", folderId: "root-id" });
  expect(drawer.unavailableReason).toBeUndefined();
  expect(probe.legacyRequests).toEqual([]);
});

it("keeps document bulk controls visible but disables processing, ZIP and deletion", async () => {
  probe.folders = probe.folders.filter((f) => !f.parent_id);
  probe.documents = [
    {
      id: "document",
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
  for (const name of ["delete", "download", "includeInSearch"]) {
    const button = action(`bulkActions.${name}`) as HTMLButtonElement;
    expect(button).not.toBeNull();
    expect(button.disabled).toBe(true);
    await act(async () => button.click());
  }
  expect(probe.deletes).toEqual([]);
  expect(probe.confirm).toBeUndefined();
  expect(probe.legacyRequests).toEqual([]);
});
