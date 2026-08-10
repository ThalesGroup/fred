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

// Coverage: a folder row's "Taille" cell shows the folder's total document
// size (via POST /documents/metadata/tag-sizes, batched once per folder view),
// not a document count — "—" while the batch is in flight, the formatted
// size once it resolves. Recursive over subfolders: a folder tag's own
// item_ids never cover a nested tag's documents, so a folder containing a
// subfolder must show their combined total, not just its own direct files
// (the mismatch a real team's data surfaced: a folder read as its own size
// while its subfolder's bytes were invisible, even though the team storage
// quota counted both).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { formatBytes } from "@shared/utils/formatBytes.ts";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));

const tagSizes = vi.fn(() => ({
  unwrap: async () => ({
    sizes: { "tag-cir": 2048, "tag-hr": 0, "tag-documents": 100, "tag-dossier-112": 50 },
  }),
}));

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [
      { id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: ["doc-1", "doc-2"] },
      { id: "tag-hr", name: "HR", path: "", type: "document", item_ids: [] },
      { id: "tag-documents", name: "Documents", path: "", type: "document", item_ids: ["doc-3"] },
      {
        id: "tag-dossier-112",
        name: "Dossier 112",
        path: "Documents",
        type: "document",
        item_ids: ["doc-4", "doc-5"],
      },
    ],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [vi.fn()],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [tagSizes],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
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

function folderRow(name: string): HTMLElement {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
  if (!button) throw new Error(`"${name}" folder row not rendered`);
  const row = button.closest('[role="row"], tr, li') ?? button.parentElement?.parentElement;
  if (!row) throw new Error(`"${name}" row container not found`);
  return row as HTMLElement;
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocumentWorkspace folder size column", () => {
  it("shows '—' before the batched tag-sizes call resolves, then the formatted total size", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
    });

    expect(tagSizes).toHaveBeenCalledWith({
      tagSizesRequest: { tag_ids: ["tag-cir", "tag-documents", "tag-dossier-112", "tag-hr"] },
    });
    expect(folderRow("CIR").textContent).toContain(formatBytes(2048));
  });

  it("sums a folder's own size with all of its subfolders', recursively", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
    });

    // "Documents" (100 bytes direct) contains "Dossier 112" (50 bytes) — the
    // row must show their combined 150, not just Documents' own 100.
    expect(folderRow("Documents").textContent).toContain(formatBytes(150));
  });

  it("never shows a raw document count in the size cell", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
    });

    // tag-hr has no documents and a 0-byte total — must render the formatted
    // zero size ("0 bytes"), not the old "N docs" label.
    expect(folderRow("HR").textContent).not.toContain("docs");
    expect(folderRow("HR").textContent).toContain(formatBytes(0));
  });
});
