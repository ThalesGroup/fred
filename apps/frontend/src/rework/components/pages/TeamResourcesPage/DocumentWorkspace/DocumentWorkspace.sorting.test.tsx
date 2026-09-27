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

// The resources table orders server-side: only one page of a tag is returned,
// so the ordering has to travel with the browse request rather than be applied
// to the rows that came back. Covered here: the default sent on first load,
// the header cycle, and the offset reset that keeps a reader from landing in
// an unrelated slice of a freshly reordered folder.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn(), useSelector: () => [] }));

// A document has to come back: with no rows the explorer renders its empty
// state and the table — headers included — is never mounted. `total`
// deliberately exceeds one page: the ordering only matters because the
// browser never holds the whole tag.
const browse = vi.hoisted(() =>
  vi.fn((_arg: { browseDocumentsByTagRequest: Record<string, unknown> }) => ({
    unwrap: async () => ({
      documents: [
        {
          identity: { document_uid: "uid-1", title: "Report", document_name: "Report.pdf", uploaded_by: null },
          file: { file_type: "pdf", file_size_bytes: 1024 },
          source: { date_added_to_kb: "2026-07-01T00:00:00Z" },
          processing: { stages: { raw: "done", vector: "done" } },
          tags: { tag_ids: ["tag-cir"] },
        },
      ],
      total: 120,
    }),
  })),
);

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListTagsQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [browse],
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
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("../CreateFolderModal/CreateFolderModal.tsx", () => ({ default: () => null }));
vi.mock("@shared/organisms/DocumentUploadDrawer/DocumentUploadDrawer.tsx", () => ({
  DocumentUploadDrawer: () => null,
}));
vi.mock("@shared/organisms/DocumentViewer/DocumentViewer.tsx", () => ({ DocumentViewer: () => null }));
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({ InlineDrawer: () => null }));

import DocumentWorkspace from "./DocumentWorkspace";

let container: HTMLDivElement;
let root: Root;

/** Every browse request issued so far, oldest first. */
function requests(): Record<string, unknown>[] {
  return browse.mock.calls.map((call) => call[0].browseDocumentsByTagRequest);
}

function lastRequest(): Record<string, unknown> {
  const all = requests();
  if (all.length === 0) throw new Error("no browse request issued");
  return all[all.length - 1];
}

function header(labelKey: string): HTMLElement {
  const match = [...container.querySelectorAll("button, th, [role='columnheader']")].find((el) =>
    el.textContent?.includes(labelKey),
  );
  if (!match) throw new Error(`no sortable header for "${labelKey}"`);
  return match as HTMLElement;
}

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

beforeEach(async () => {
  browse.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });

  // Navigate into "CIR" — a tag's documents only load once it is current.
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

describe("DocumentWorkspace — server-side ordering", () => {
  it("asks for name ascending on first load", () => {
    expect(lastRequest()).toMatchObject({ tag_id: "tag-cir", sort_by: "name", sort_order: "asc", offset: 0 });
  });

  it("switches the active column to descending on a second press", () => {
    click(header("rework.resources.columns.name"));
    expect(lastRequest()).toMatchObject({ sort_by: "name", sort_order: "desc" });
  });

  it("keeps flipping the active column instead of clearing the sort", () => {
    // Regression: the header used to cycle asc -> desc -> cleared, and a
    // cleared server sort has to fall back to a default column — so a third
    // press on "Size" visibly moved the sort to "Name".
    const sizeHeader = header("rework.resources.columns.size");
    click(sizeHeader);
    expect(lastRequest()).toMatchObject({ sort_by: "size", sort_order: "asc" });

    click(sizeHeader);
    expect(lastRequest()).toMatchObject({ sort_by: "size", sort_order: "desc" });

    click(sizeHeader);
    expect(lastRequest()).toMatchObject({ sort_by: "size", sort_order: "asc" });
  });

  it("orders by another column when its header is pressed", () => {
    click(header("rework.resources.columns.created"));
    expect(lastRequest()).toMatchObject({ sort_by: "created", sort_order: "asc" });

    click(header("rework.resources.columns.size"));
    expect(lastRequest()).toMatchObject({ sort_by: "size", sort_order: "asc" });
  });

  it("goes back to the first page when the ordering changes", () => {
    const next = container.querySelector('button[aria-label="dataTable.pagination.next"]');
    if (!next) throw new Error("pagination controls not rendered");
    click(next);
    expect(lastRequest()).toMatchObject({ offset: 50 });

    click(header("rework.resources.columns.size"));

    // Page 2 of a name-ordered folder holds different documents than page 2 of
    // a size-ordered one — keeping the offset would drop the reader into an
    // unrelated slice.
    expect(lastRequest()).toMatchObject({ sort_by: "size", offset: 0 });
  });

  it("does not make the uploader column sortable", () => {
    expect(() => header("rework.resources.columns.author")).toThrow();
  });
});
