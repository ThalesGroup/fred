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

// Active ingestion has no user cancellation action and prevents document deletion.

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
// Forward the (mocked) selector's own return value — the live task map is the
// unit under test here.
vi.mock("react-redux", () => ({ useSelector: (selector: () => unknown) => selector() }));

const rawDoc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: false },
  processing: { stages: {} },
  tags: { tag_ids: ["tag-cir"] },
});

const runningTask = {
  taskId: "task-to-cancel",
  kind: "ingestion",
  target: { type: "document", id: "uid-running", label: "Running doc.pdf" },
  owner: null,
  localOnly: false,
  state: "running",
  progress: null,
  step: "processing",
  error: null,
  lastSeq: 2,
  registeredAt: 0,
  terminalAt: null,
  acknowledgedAt: null,
  warnings: null,
};

const cancelTask = vi.fn(() => ({ unwrap: async () => ({}) }));
const showConfirmationDialog = vi.fn();

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListTagsQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({
      unwrap: async () => ({
        documents: [rawDoc("uid-running", "Running doc"), rawDoc("uid-norun", "Quiet doc")],
        total: 2,
      }),
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagMutation: () => [vi.fn()],
  useDeleteTagMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [cancelTask],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({}) })),
  ],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({
  selectActiveTasks: () => [runningTask],
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
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({ InlineDrawer: () => null }));

import DocumentWorkspace from "./DocumentWorkspace";

let container: HTMLDivElement;
let root: Root;

beforeEach(async () => {
  cancelTask.mockClear();
  showConfirmationDialog.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });

  const cir = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("CIR"));
  if (!cir) throw new Error('"CIR" folder row not rendered');
  await act(async () => {
    cir.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  document.querySelectorAll('[role="presentation"]').forEach((el) => el.remove());
});

function moreButtons(): HTMLButtonElement[] {
  return [...container.querySelectorAll('button[aria-label="rework.resources.action.more"]')] as HTMLButtonElement[];
}

/** The menu portals into document.body, outside `container`. */
function openMenu(button: HTMLButtonElement): Element[] {
  act(() => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  return [
    ...document.querySelectorAll(
      '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
    ),
  ];
}

describe("DocumentWorkspace — ingestion cannot be cancelled", () => {
  it("does not offer cancellation for a document with a running task", () => {
    const items = openMenu(moreButtons()[0]);
    expect(items.find((el) => el.textContent?.includes("rework.resources.action.stopIngestion"))).toBeUndefined();
    expect(cancelTask).not.toHaveBeenCalled();
    expect(showConfirmationDialog).not.toHaveBeenCalled();
  });

  it("does not offer 'Stop ingestion' for a document with no active task", () => {
    const items = openMenu(moreButtons()[1]);
    expect(items.find((el) => el.textContent?.includes("rework.resources.action.stopIngestion"))).toBeUndefined();
  });

  it("greys out 'Delete' while the ingestion is live", () => {
    const items = openMenu(moreButtons()[0]);
    const deleteItem = items.find((el) => el.textContent?.includes("rework.resources.action.delete"));
    expect(deleteItem).toBeTruthy();
    const li = deleteItem!.closest("li") ?? deleteItem!;
    expect(li.getAttribute("data-disabled")).toBe("true");
    // The reason is discoverable on hover (native title), not a permanent
    // second line — per developer request on #2315.
    expect(li.getAttribute("title")).toBe("rework.resources.action.deleteDisabledWhileProcessing");
  });

  it("keeps 'Delete' clickable for a document with no active task", () => {
    const items = openMenu(moreButtons()[1]);
    const deleteItem = items.find((el) => el.textContent?.includes("rework.resources.action.delete"));
    expect(deleteItem).toBeTruthy();
    const li = deleteItem!.closest("li") ?? deleteItem!;
    expect(li.getAttribute("data-disabled")).toBe("false");
  });
});
