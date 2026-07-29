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

// Coverage for the "Download" action (RFC KNOWLEDGE-WORKSPACE-REWORK-RFC.md
// §13.13): a per-row entry in the "more" menu, just under "Renommer" —
// moved there from a standalone icon per a later request — and a bulk zip
// download wired into BulkActionsBar once 2+ rows are selected.

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

const doc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z" },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
});

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({ unwrap: async () => ({ documents: [doc("uid-1", "Report")], total: 1 }) }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [] }));
vi.mock("../../../../features/tasks/useRefetchOnTaskSuccess", () => ({ useRefetchOnTaskSuccess: () => {} }));
vi.mock("../../../../features/tasks/useNotifyOnNewTaskTarget", () => ({ useNotifyOnNewTaskTarget: () => {} }));

const commands = vi.hoisted(() => ({
  download: vi.fn(),
  fetchBlob: vi.fn(async () => new Blob(["x"])),
}));
vi.mock("../../../../../components/documents/common/useDocumentCommands", () => ({
  useDocumentCommands: () => ({
    previewTarget: null,
    closePreview: () => {},
    preview: () => {},
    download: commands.download,
    fetchBlob: commands.fetchBlob,
    toggleRetrievable: async () => {},
    removeFromLibrary: async () => {},
  }),
}));

const downloadUtils = vi.hoisted(() => ({ downloadManyAsZip: vi.fn() }));
vi.mock("../../../../../utils/downloadUtils.tsx", () => ({
  downloadManyAsZip: downloadUtils.downloadManyAsZip,
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
  commands.download.mockClear();
  commands.fetchBlob.mockClear();
  downloadUtils.downloadManyAsZip.mockClear();

  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });

  // Navigate into "CIR" — its documents only load once it's the current folder.
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

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function rowCheckbox(): HTMLInputElement {
  const boxes = [...container.querySelectorAll('input[type="checkbox"]')];
  const box = boxes[1];
  if (!box) throw new Error("row checkbox not rendered");
  return box as HTMLInputElement;
}

/** Opens the row's "more" menu (portaled into document.body) and clicks the item
 *  whose label key contains `labelKeySuffix`. */
function clickMoreMenuItem(labelKeySuffix: string) {
  const moreButton = container.querySelector('button[aria-label="rework.resources.action.more"]');
  if (!moreButton) throw new Error("more-menu trigger not rendered");
  click(moreButton);

  const items = [...document.querySelectorAll('[role="presentation"] li, [role="presentation"] button')];
  const item = items.find((el) => el.textContent?.includes(labelKeySuffix));
  if (!item) throw new Error(`menu item containing "${labelKeySuffix}" not found`);
  click(item);
}

describe("DocumentWorkspace — per-row download (more menu, just under Renommer)", () => {
  it("calls commands.download for that document when 'Download' is selected from the more menu", () => {
    clickMoreMenuItem("rework.resources.action.download");

    expect(commands.download).toHaveBeenCalledOnce();
    expect(commands.download.mock.calls[0][0].identity.document_uid).toBe("uid-1");
  });

  it("lists Download right after Rename in the more menu", () => {
    const moreButton = container.querySelector('button[aria-label="rework.resources.action.more"]');
    click(moreButton);

    const items = [...document.querySelectorAll('[role="presentation"] li')];
    const labels = items.map((el) => el.textContent ?? "");
    const renameIndex = labels.findIndex((label) => label.includes("rework.resources.action.rename"));
    const downloadIndex = labels.findIndex((label) => label.includes("rework.resources.action.download"));

    expect(renameIndex).toBeGreaterThanOrEqual(0);
    expect(downloadIndex).toBe(renameIndex + 1);
  });
});

describe("DocumentWorkspace — bulk download", () => {
  it("zips the selected document(s) when the bulk download button is clicked", () => {
    act(() => {
      rowCheckbox().click();
    });
    const bulkDownloadButton = container.querySelector('button[aria-label="rework.resources.bulkActions.download"]');
    expect(bulkDownloadButton).not.toBeNull();

    click(bulkDownloadButton);

    expect(downloadUtils.downloadManyAsZip).toHaveBeenCalledOnce();
    const [files, zipFilename] = downloadUtils.downloadManyAsZip.mock.calls[0];
    expect(files).toHaveLength(1);
    expect(files[0].filename).toBe("Report.pdf");
    expect(zipFilename).toBe("resources.zip");
  });

  it("shows the download button as loading while the zip is being built, then clears it", async () => {
    let resolveDownload!: () => void;
    downloadUtils.downloadManyAsZip.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          resolveDownload = resolve;
        }),
    );

    act(() => {
      rowCheckbox().click();
    });
    const bulkDownloadButton = () =>
      container.querySelector('button[aria-label="rework.resources.bulkActions.download"]') as HTMLButtonElement;
    click(bulkDownloadButton());

    expect(bulkDownloadButton().disabled).toBe(true);
    expect(bulkDownloadButton().getAttribute("aria-busy")).toBe("true");

    await act(async () => {
      resolveDownload();
      await Promise.resolve();
    });

    expect(bulkDownloadButton().disabled).toBe(false);
    expect(bulkDownloadButton().getAttribute("aria-busy")).toBe("false");
  });
});
