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

// Coverage (#2315 live status): the row badge must reflect the LIVE ingestion
// task from the SSE feed, not only the browse snapshot's `processing.stages`.
// A document whose snapshot still reads "raw" but that has an active task
// (target.type === "document", target.id === document_uid) renders
// "processing" immediately; a document with no active task keeps deriving from
// its snapshot ("raw"/"En attente"). This is the regression test for the
// upload that used to sit on "En attente" for its whole run and jump straight
// to done without ever showing "Traitement…".

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
// The component reads the task feed through useSelector(selectActiveTasks) —
// forward the (mocked) selector's own return value instead of a hardcoded [].
vi.mock("react-redux", () => ({ useSelector: (selector: () => unknown) => selector() }));

const rawDoc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: false },
  processing: { stages: {} },
  tags: { tag_ids: ["tag-cir"] },
});

const runningTask = {
  taskId: "task-live",
  kind: "ingestion",
  target: { type: "document", id: "uid-live", label: "Live doc.pdf" },
  owner: null,
  localOnly: false,
  state: "running",
  progress: 0.4,
  step: "processing",
  error: null,
  lastSeq: 3,
  registeredAt: 0,
  terminalAt: null,
  acknowledgedAt: null,
  warnings: null,
};

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({
      unwrap: async () => ({
        documents: [rawDoc("uid-live", "Live doc"), rawDoc("uid-idle", "Idle doc")],
        total: 2,
      }),
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
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

beforeEach(async () => {
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
});

function rowFor(name: string): HTMLElement {
  const nameCell = [...container.querySelectorAll("span")].find((el) => el.textContent === name);
  if (!nameCell) throw new Error(`row for "${name}" not found`);
  const row = nameCell.closest('[class*="datatable-row"]');
  if (!row) throw new Error(`row container for "${name}" not found`);
  return row as HTMLElement;
}

describe("DocumentWorkspace — live task drives the status badge", () => {
  it("shows 'processing' for a document whose snapshot is raw but whose ingestion task is running", () => {
    expect(rowFor("Live doc.pdf").textContent).toContain("rework.resources.status.processing");
  });

  it("keeps deriving from the snapshot for a document with no active task", () => {
    expect(rowFor("Idle doc.pdf").textContent).toContain("rework.resources.status.raw");
    expect(rowFor("Idle doc.pdf").textContent).not.toContain("rework.resources.status.processing");
  });
});
