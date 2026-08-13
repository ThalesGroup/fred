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

// Coverage (#2315 error detail): hovering a failed document's "failed" status
// chip shows each failed stage with the message persisted in
// `processing.errors` — the detail rides the chip itself, with no menu entry
// and no modal (the row menu must not offer one).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // Appends interpolation values so assertions can see them (the stage label
    // renders as `t("...errorTooltip.stage", { stage })`).
    t: (key: string, params?: Record<string, unknown>) =>
      params && "stage" in params ? `${key} ${String(params.stage)}` : key,
    i18n: { language: "en" },
  }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));

const failedDoc = {
  identity: { document_uid: "uid-failed", title: "Broken", document_name: "Broken.pdf", uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: false },
  processing: {
    stages: { preview: "failed", vector: "not_started" },
    errors: { preview: "Execution timed_out" },
  },
  tags: { tag_ids: ["tag-cir"] },
};

const readyDoc = {
  identity: { document_uid: "uid-ready", title: "Fine", document_name: "Fine.pdf", uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-08-01T00:00:00Z", retrievable: true },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
};

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({ unwrap: async () => ({ documents: [failedDoc, readyDoc], total: 2 }) }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
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

describe("DocumentWorkspace — ingestion error detail on the status chip", () => {
  it("shows each failed stage and its message when hovering the failed chip", () => {
    const chip = [...container.querySelectorAll("span")].find((el) =>
      el.textContent?.includes("rework.resources.status.failed"),
    );
    expect(chip).toBeTruthy();

    // React derives onMouseEnter from the bubbling `mouseover` (see Tooltip.test).
    act(() => {
      chip!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });

    const tooltip = document.querySelector('[role="tooltip"]');
    expect(tooltip).not.toBeNull();
    expect(tooltip!.textContent).toContain("preview");
    expect(tooltip!.textContent).toContain("Execution timed_out");
  });

  it("no longer offers an 'Error details' entry in the failed document's row menu", () => {
    const items = openMenu(moreButtons()[0]);
    expect(items.length).toBeGreaterThan(0);
    expect(items.find((el) => el.textContent?.includes("rework.resources.action.errorDetail"))).toBeUndefined();
  });
});
