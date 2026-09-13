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

// Coverage: this workspace now sits one level below a list of knowledge bases,
// and shows exactly one of them. Fred's own is the team corpus minus every
// library a contributor fills; a contributed base is rooted at its library and
// offers no action over it. The folder view itself is untouched — with no
// scope at all, it still shows the whole corpus, which is what every other
// DocumentWorkspace test renders.

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

// "Local-2" is the library a Knowledge Base fills, top-level like every
// library, with one sub-folder the pod mirrored from the source.
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

import DocumentWorkspace, { type KnowledgeBaseScope } from "./DocumentWorkspace";

let container: HTMLDivElement;
let root: Root;

async function render(props: { knowledgeBase?: KnowledgeBaseScope; onLeaveKnowledgeBase?: () => void } = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} {...props} />);
  });
}

/** Folder names in the table's Name column. Each cell renders the folder glyph
 *  as text before the name, so that prefix is stripped. */
function folderNames(): string[] {
  return Array.from(container.querySelectorAll('[class*="nameButton"]')).map((cell) =>
    (cell.textContent ?? "").replace(/^folder/, ""),
  );
}

function hasAction(ariaLabel: string): boolean {
  return container.querySelector(`[aria-label="${ariaLabel}"]`) !== null;
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocumentWorkspace knowledge base scope", () => {
  it("shows the whole corpus when no scope is given", async () => {
    await render();
    expect(folderNames().sort()).toEqual(["CIR", "Local-2", "Rags"]);
  });

  it("leaves the contributed libraries out of Fred's own base", async () => {
    await render({
      knowledgeBase: { kind: "native", label: "Fred", contributedLibraryIds: new Set(["tag-local"]) },
    });

    // Local-2 is a knowledge base of its own, one level up — not a folder here.
    expect(folderNames().sort()).toEqual(["CIR", "Rags"]);
  });

  it("roots a contributed base at its library, showing what the pod mirrored into it", async () => {
    await render({ knowledgeBase: { kind: "contributed", label: "Local-2", libraryId: "tag-local" } });

    expect(folderNames()).toEqual(["src"]);
    // The root segment names the base, and nothing above it leaks the corpus.
    expect(container.textContent).toContain("Local-2");
    expect(container.textContent).not.toContain("CIR");
  });

  it("withholds every action over a contributed base, and keeps them over Fred's own", async () => {
    await render({ knowledgeBase: { kind: "contributed", label: "Local-2", libraryId: "tag-local" } });
    expect(hasAction("rework.resources.menu.newFolder")).toBe(false);
    expect(hasAction("rework.resources.action.addFile")).toBe(false);
    expect(hasAction("rework.resources.action.refresh")).toBe(true);

    await act(async () => {
      root.render(
        <DocumentWorkspace
          teamId="team-1"
          isPersonalTeam={false}
          knowledgeBase={{ kind: "native", label: "Fred", contributedLibraryIds: new Set(["tag-local"]) }}
        />,
      );
    });
    expect(hasAction("rework.resources.menu.newFolder")).toBe(true);
  });

  it("shows nothing, never the corpus, for a library the tag list does not carry", async () => {
    // findNode falls back to the tree root for a path it cannot walk, so a base
    // whose library has not loaded (created seconds ago, deleted elsewhere)
    // would otherwise show the whole team corpus under that base's name.
    await render({ knowledgeBase: { kind: "contributed", label: "Nouveau", libraryId: "tag-unknown" } });

    expect(folderNames()).toEqual([]);
    expect(container.textContent).not.toContain("CIR");
  });

  it("offers a way back to the list only when the page gives it one", async () => {
    const onLeave = vi.fn();
    await render({
      knowledgeBase: { kind: "native", label: "Fred", contributedLibraryIds: new Set() },
      onLeaveKnowledgeBase: onLeave,
    });

    const leave = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("rework.resources.knowledgeBases.title"),
    );
    expect(leave).toBeDefined();
    act(() => {
      leave?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(onLeave).toHaveBeenCalledOnce();
  });
});
