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

// Rooted at one library, this workspace must show that library and nothing
// else. The failure worth a test of its own is the library that cannot be
// found: "no root requested" and "the requested root is gone" both reduce to a
// null path, and a rooted tree is built from every tag the team has — so the
// unguarded version answers "show me one library" with the whole corpus. A
// library outliving its folder is a supported state, not a corrupt one:
// deleting a machine-filled folder stays available to people.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListTagsQuery: () => ({
    data: [
      { id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] },
      {
        id: "tag-lib",
        name: "WebDav-1",
        path: "",
        type: "document",
        item_ids: [],
        synchronized_by: "knowledge_base:i1",
      },
      { id: "tag-guides", name: "guides", path: "WebDav-1", type: "document", item_ids: [] },
    ],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [vi.fn()],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagMutation: () => [vi.fn()],
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

function render(rootTagId?: string) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} rootTagId={rootTagId} readOnly />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

/** Folder rows are buttons carrying the folder's name. */
function rowNames(): string[] {
  return [...container.querySelectorAll("button")].map((b) => b.textContent ?? "");
}

describe("DocumentWorkspace rooted at a library", () => {
  it("shows what the library holds and nothing beside it", () => {
    render("tag-lib");
    const names = rowNames().join(" ");
    expect(names).toContain("guides");
    expect(names).not.toContain("CIR");
  });

  it("shows nothing when the library it was rooted at is gone", () => {
    // The corpus is what must not appear: the page was asked for one library.
    render("tag-missing");
    const names = rowNames().join(" ");
    expect(names).not.toContain("CIR");
    expect(names).not.toContain("WebDav-1");
    expect(names).not.toContain("guides");
  });

  it("still lists the corpus when no library was asked for", () => {
    // Guards the fix against over-reaching: unrooted behaviour is untouched,
    // machine-filled libraries excepted.
    render(undefined);
    const names = rowNames().join(" ");
    expect(names).toContain("CIR");
    expect(names).not.toContain("WebDav-1");
  });
});
