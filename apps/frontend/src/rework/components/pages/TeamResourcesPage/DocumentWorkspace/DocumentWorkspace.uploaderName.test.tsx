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

// Coverage: the "Ajouté par" column resolves a document's uploaded_by uid to
// a display name via a batched lookup keyed by every uid currently in view.
// A freshly-uploaded document adds a brand-new uid to that key set, which
// starts a fresh fetch — while it's in flight the uid has no entry in the
// resolved map yet, but that's "not resolved yet", not "no such user". The
// column must show a neutral placeholder during that window, not the raw
// uid (the regression this covers: the uploader's UUID briefly flashed in
// place of their name for a just-uploaded doc).

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
vi.mock("react-redux", () => ({ useSelector: () => [] }));

const doc = (uid: string, name: string, uploadedBy: string | null) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: uploadedBy },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z", retrievable: true },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
});

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({
      unwrap: async () => ({
        documents: [doc("uid-fresh", "Fresh upload", "c2f1ce79-b102-48a8-9d80-e825de4ff93d")],
        total: 1,
      }),
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
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
  useConfirmationDialog: () => ({ showConfirmationDialog: () => {} }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));

// Mutable per-test: mimics the batched uploader-lookup RTK Query hook mid-fetch
// vs. settled, without needing a real store/network layer.
let uploadersQueryResult: { data: { id: string; first_name?: string; last_name?: string }[]; isFetching: boolean } = {
  data: [],
  isFetching: true,
};

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: { id: "team-1" } }),
  useUsersByIdsQuery: () => uploadersQueryResult,
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

async function renderIntoCirFolder() {
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });
  const cir = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("CIR"));
  if (!cir) throw new Error('"CIR" folder row not rendered');
  await act(async () => {
    cir.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function rowFor(name: string): HTMLElement {
  const nameCell = [...container.querySelectorAll("span")].find((el) => el.textContent === name);
  if (!nameCell) throw new Error(`row for "${name}" not found`);
  const row = nameCell.closest('[class*="datatable-row"]');
  if (!row) throw new Error(`row container for "${name}" not found`);
  return row as HTMLElement;
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocumentWorkspace — uploader name column", () => {
  it("shows a placeholder, not the raw uid, while the uploader lookup is still in flight", async () => {
    uploadersQueryResult = { data: [], isFetching: true };
    await renderIntoCirFolder();
    const cell = rowFor("Fresh upload.pdf").textContent ?? "";
    expect(cell).not.toContain("c2f1ce79-b102-48a8-9d80-e825de4ff93d");
  });

  it("resolves to the display name once the uploader lookup settles", async () => {
    uploadersQueryResult = {
      data: [{ id: "c2f1ce79-b102-48a8-9d80-e825de4ff93d", first_name: "Arthur", last_name: "Adam" }],
      isFetching: false,
    };
    await renderIntoCirFolder();
    const cell = rowFor("Fresh upload.pdf").textContent ?? "";
    expect(cell).toContain("Arthur Adam");
    expect(cell).not.toContain("c2f1ce79-b102-48a8-9d80-e825de4ff93d");
  });

  it("falls back to the raw uid once the lookup has settled and genuinely found no match", async () => {
    uploadersQueryResult = { data: [], isFetching: false };
    await renderIntoCirFolder();
    const cell = rowFor("Fresh upload.pdf").textContent ?? "";
    expect(cell).toContain("c2f1ce79-b102-48a8-9d80-e825de4ff93d");
  });
});
