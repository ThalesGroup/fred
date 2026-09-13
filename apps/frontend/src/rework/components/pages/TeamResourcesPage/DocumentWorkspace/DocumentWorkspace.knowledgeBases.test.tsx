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

// Coverage: the corpus root reads as the team's knowledge bases — Fred's own
// heading the folders it holds, each contributed library a sibling badged with
// the name its contributor declared. A presentation of the same rows, not a
// level of its own: the folders stay exactly one click from the page, which is
// where they have always been.

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

// "Local-2" is the library a Knowledge Base fills — top-level like every
// library, with one sub-folder its pod mirrored out of the source.
const TAGS = [
  { id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] },
  { id: "tag-rags", name: "Rags", path: "", type: "document", item_ids: [] },
  { id: "tag-local", name: "Local-2", path: "", type: "document", item_ids: [] },
  { id: "tag-local-src", name: "src", path: "Local-2", type: "document", item_ids: [] },
];

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({ data: TAGS, isLoading: false, refetch: () => {} }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({ documents: [], total: 0 }) })),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({ sizes: {} }) })),
  ],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [vi.fn()],
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

/** "GitHub" is what this contributor declared, and the only thing the badge
 *  knows about it — nothing here maps it to an icon or a behaviour. */
const CONTRIBUTED = new Map([["tag-local", "GitHub"]]);

let container: HTMLDivElement;
let root: Root;

async function render(synchronizedLibraries?: ReadonlyMap<string, string>) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <DocumentWorkspace teamId="team-1" isPersonalTeam={false} synchronizedLibraries={synchronizedLibraries} />,
    );
  });
}

/** Every table row, as its text — the folder glyph renders as text, so a name
 *  cell reads "folderCIR". */
function rowTexts(): string[] {
  return Array.from(container.querySelectorAll('[class*="datatable-row"]')).map((row) => row.textContent ?? "");
}

function folderButton(name: string): HTMLElement {
  const button = Array.from(container.querySelectorAll('[class*="nameButton"]')).find(
    (candidate) => (candidate.textContent ?? "").replace(/^folder/, "") === name,
  );
  if (!button) throw new Error(`"${name}" row not rendered`);
  return button as HTMLElement;
}

function click(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocumentWorkspace corpus root — knowledge bases", () => {
  it("shows Fred's folders straight away, under the row naming its knowledge base", async () => {
    await render(CONTRIBUTED);
    const rows = rowTexts();

    // The whole point: no navigation happened, and CIR is already on screen.
    expect(rows[0]).toContain("rework.resources.knowledgeBases.nativeName");
    expect(rows[0]).toContain("rework.resources.knowledgeBases.manualDeposit");
    expect(rows.some((row) => row.includes("CIR"))).toBe(true);
    expect(rows.some((row) => row.includes("Rags"))).toBe(true);
  });

  it("sets Fred's own folders in under its row, and not a contributed library", async () => {
    await render(CONTRIBUTED);

    expect(folderButton("CIR").hasAttribute("data-nested")).toBe(true);
    expect(folderButton("Local-2").hasAttribute("data-nested")).toBe(false);
  });

  it("badges a contributed library with the name its contributor declared, after Fred's folders", async () => {
    await render(CONTRIBUTED);
    const rows = rowTexts();

    const contributed = rows.findIndex((row) => row.includes("Local-2"));
    expect(rows[contributed]).toContain("GitHub");
    expect(rows[contributed]).toContain("rework.resources.knowledgeBases.readOnly");
    // Fred's own come first; a contributed base is a sibling below them.
    expect(contributed).toBeGreaterThan(rows.findIndex((row) => row.includes("Rags")));
  });

  it("offers neither a row menu nor a checkbox over a contributed library", async () => {
    await render(CONTRIBUTED);

    // Deleting that library's tag from here would leave its Knowledge Base
    // filling a folder that no longer exists.
    const boxes = container.querySelectorAll('input[type="checkbox"]');
    // select-all + CIR + Rags — not the grouping row, not Local-2.
    expect(boxes).toHaveLength(3);

    click(folderButton("Local-2"));
    // Inside it, the actions are withheld as they already were.
    expect(container.querySelector('[aria-label="rework.resources.menu.newFolder"]')).toBeNull();
  });

  it("keeps the folder view itself untouched one level in", async () => {
    await render(CONTRIBUTED);
    click(folderButton("CIR"));

    // No grouping row and no inset below the root — just the folder.
    expect(rowTexts().some((row) => row.includes("rework.resources.knowledgeBases.manualDeposit"))).toBe(false);
    // The crumb says which knowledge base you walked into.
    expect(container.textContent).toContain("rework.resources.knowledgeBases.nativeName");
    expect(container.textContent).toContain("CIR");
  });

  it("names Fred even when the team has connected nothing", async () => {
    await render();
    expect(rowTexts()[0]).toContain("rework.resources.knowledgeBases.nativeName");
    expect(rowTexts().some((row) => row.includes("rework.resources.knowledgeBases.readOnly"))).toBe(false);
  });
});
