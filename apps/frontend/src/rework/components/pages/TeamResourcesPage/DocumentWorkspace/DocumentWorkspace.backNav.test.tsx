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

// Coverage for the toolbar's back button: it returns to whichever folder was
// actually visited before, which is not necessarily the current folder's
// parent (e.g. jumping between two unrelated top-level folders).

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
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [
      { id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] },
      { id: "tag-hr", name: "HR", path: "", type: "document", item_ids: [] },
      { id: "tag-reports", name: "Reports", path: "CIR", type: "document", item_ids: [] },
    ],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [vi.fn()],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [], selectAllTasks: () => [] }));
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

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function folderButton(name: string): HTMLButtonElement {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
  if (!button) throw new Error(`folder row "${name}" not rendered`);
  return button;
}

// Always mounted (never conditionally rendered) so it keeps reserving its
// layout space next to the breadcrumb — "hidden" means disabled +
// visibility: hidden, not unmounted, or the breadcrumb would shift left
// every time the button appears/disappears.
function backButton(): HTMLButtonElement {
  const button = container.querySelector('button[aria-label="rework.resources.action.back"]');
  if (!button) throw new Error("back button not rendered");
  return button as HTMLButtonElement;
}

function backButtonIsHidden(): boolean {
  const button = backButton();
  return button.hasAttribute("disabled") && button.style.visibility === "hidden";
}

function visibleFolderNames(): string[] {
  const buttonTexts = [...container.querySelectorAll("button")].map((b) => b.textContent ?? "");
  return ["CIR", "HR", "Reports"].filter((name) => buttonTexts.some((text) => text.includes(name)));
}

describe("DocumentWorkspace back navigation", () => {
  it("keeps the back button mounted but hidden (disabled + invisible, not unmounted) at the root", () => {
    // Mounted (not unmounted) so the breadcrumb next to it never shifts.
    expect(() => backButton()).not.toThrow();
    expect(backButtonIsHidden()).toBe(true);
  });

  it("returns to the previously visited folder, not necessarily the parent", () => {
    // Root -> HR -> CIR (a sibling, not HR's parent or child) -> back should
    // land on HR again, not on root (which "go to parent" would do instead).
    click(folderButton("HR"));
    expect(visibleFolderNames()).toEqual([]); // HR has no children in this mock

    click(backButton());
    expect(visibleFolderNames()).toEqual(["CIR", "HR"]);

    click(folderButton("CIR"));
    expect(visibleFolderNames()).toEqual(["Reports"]);

    expect(backButtonIsHidden()).toBe(false);
    click(backButton());
    expect(visibleFolderNames()).toEqual(["CIR", "HR"]);
  });

  it("hides the back button again once back at the root", () => {
    click(folderButton("HR"));
    click(backButton());
    expect(backButtonIsHidden()).toBe(true);
  });

  // Regression: navigating to root via the breadcrumb's own root segment
  // still pushes onto the history stack (like any other navigateTo call),
  // so a history-length check alone stayed non-empty and left the button
  // visible even at the root. Hidden must track "are we at the root"
  // (currentFolderFull), not "is there history to pop".
  it("hides the back button when root is reached via the breadcrumb, not just via the back button itself", () => {
    click(folderButton("CIR"));
    expect(backButtonIsHidden()).toBe(false);

    // The breadcrumb's root segment — not the back button — brings us home.
    // (`t` is mocked to return the raw key, so the root label is the key itself.)
    const rootCrumb = [...container.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("rework.resources.roots.resources"),
    );
    if (!rootCrumb) throw new Error("breadcrumb root segment not rendered");
    click(rootCrumb);

    // navigateTo(null) still pushes onto the history stack like any other
    // navigation, so a history-length-based check would stay non-empty here
    // — hidden must track "are we at the root", not "is there history".
    expect(backButtonIsHidden()).toBe(true);
  });

  // Regression: breadcrumbSegments built its intermediate segments' onClick
  // by closing over a single `let acc` mutated across the whole forEach —
  // every segment's closure shared that one binding, so by the time any of
  // them actually fired (a later click), `acc` held whatever the loop left
  // it at (the deepest path), not the segment that was clicked. Clicking a
  // non-root, non-last crumb was a silent no-op: it "navigated" to the
  // folder you were already in.
  it("navigates to an intermediate breadcrumb segment (parent), not just root or the current folder", () => {
    click(folderButton("CIR"));
    click(folderButton("Reports")); // now two levels deep, inside Reports

    // "CIR" here can only be the breadcrumb's own segment: Reports has no
    // child folders, so no CIR folder row exists at this depth.
    click(folderButton("CIR"));

    // Back at CIR: its child folder row ("Reports") is visible again.
    // Under the bug, the click was a no-op (stayed inside Reports, whose
    // only "CIR"/"Reports"-matching button is the breadcrumb's own CIR
    // crumb — never a "Reports" row).
    expect(visibleFolderNames()).toEqual(["Reports"]);
  });
});
