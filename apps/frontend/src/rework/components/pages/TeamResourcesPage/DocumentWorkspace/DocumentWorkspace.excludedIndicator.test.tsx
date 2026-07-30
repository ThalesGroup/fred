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

// Coverage: a document excluded from search (source.retrievable === false)
// shows an error-colored indicator icon at the end of its row, just left of
// the Preview icon button — visible only for that state, not for a
// retrievable (or not-yet-stamped) document. Also covers a tabular dataset
// (CSV/XLSX, only the `sql` stage ever completes): `retrievable` stays false
// there by design (RAG-DATASET-DISCOVERY-RFC.md, no vector chunks emitted
// unless dataset pointer chunks are enabled), so the indicator must stay
// hidden — it isn't a real exclusion for that content type.

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

const doc = (uid: string, name: string, retrievable: boolean | undefined) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z", retrievable },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
});

const tabularDoc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.xlsx`, uploaded_by: null },
  file: { file_type: "xlsx", file_size_bytes: 2048 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z", retrievable: false },
  processing: { stages: { raw: "done", sql: "done" } },
  tags: { tag_ids: ["tag-cir"] },
});

// `retrievable` is stamped false at registration and only flips true once
// vectorization completes (base_input_processor.py / vectorization_processor.py)
// — so a still-processing document also has retrievable === false, without
// anyone having excluded it.
const processingDoc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z", retrievable: false },
  processing: { stages: { raw: "done", vector: "in_progress" } },
  tags: { tag_ids: ["tag-cir"] },
});

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({
      unwrap: async () => ({
        documents: [
          doc("uid-excluded", "Excluded doc", false),
          doc("uid-included", "Included doc", true),
          doc("uid-unset", "Unset doc", undefined),
          tabularDoc("uid-tabular", "Tabular doc"),
          processingDoc("uid-processing", "Processing doc"),
        ],
        total: 5,
      }),
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
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

describe("DocumentWorkspace — excluded-from-search row indicator", () => {
  it("shows the indicator icon for a document excluded from search", () => {
    expect(
      rowFor("Excluded doc.pdf").querySelector('[aria-label="rework.resources.status.excludedFromSearch"]'),
    ).not.toBeNull();
  });

  it("hides the indicator for a retrievable document", () => {
    expect(
      rowFor("Included doc.pdf").querySelector('[aria-label="rework.resources.status.excludedFromSearch"]'),
    ).toBeNull();
  });

  it("hides the indicator when retrievable has never been stamped (undefined, not explicitly false)", () => {
    expect(
      rowFor("Unset doc.pdf").querySelector('[aria-label="rework.resources.status.excludedFromSearch"]'),
    ).toBeNull();
  });

  it("hides the indicator for a tabular dataset even though retrievable is false", () => {
    expect(
      rowFor("Tabular doc.xlsx").querySelector('[aria-label="rework.resources.status.excludedFromSearch"]'),
    ).toBeNull();
  });

  it("hides the indicator while the document is still processing, even though retrievable is false", () => {
    expect(
      rowFor("Processing doc.pdf").querySelector('[aria-label="rework.resources.status.excludedFromSearch"]'),
    ).toBeNull();
  });
});
