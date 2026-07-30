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

// Coverage for FilesystemWorkspace — the /fs counterpart of DocumentWorkspace,
// step 2 of the "bring ResourceExplorer to the other three tabs" plan
// (RFC §13.7 FRONT-09.H). Two concerns: (1) write-action gating (issue #1996
// point A.1 — a Member without CAN_UPDATE_RESOURCES must not see
// upload/new-folder on "Espace d'équipe" but keeps them on "Mon espace"),
// ported from the old TeamFilesystemBrowser.test.tsx's intent but targeting
// the new toolbar (the old test asserted single-line-row aria-labels that no
// longer exist); (2) breadcrumb navigation to an intermediate (non-root,
// non-current) segment — the same shape of regression already caught once
// for Corpus's breadcrumb (a closure-over-mutable-loop-variable bug).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// One flat directory per path — `teams/nb/shared` has a `CIR` subfolder,
// which itself has a `Reports` subfolder, mirroring the fixture already used
// for Corpus's own breadcrumb regression test.
const LS_DATA: Record<string, { path: string; type: "file" | "directory" }[]> = {
  "teams/nb/shared": [{ path: "CIR", type: "directory" }],
  "teams/nb/shared/CIR": [{ path: "Reports", type: "directory" }],
  "teams/nb/shared/CIR/Reports": [],
  "teams/nb/users/alice": [{ path: "notes.txt", type: "file" }],
};

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useLsQuery: (arg: { path: string }) => ({
    data: LS_DATA[arg.path] ?? [],
    isLoading: false,
    refetch: () => {},
  }),
  useDeleteFileMutation: () => [async () => ({ unwrap: async () => undefined })],
  useMkdirMutation: () => [async () => ({ unwrap: async () => undefined })],
  useUploadFileMutation: () => [async () => ({ unwrap: async () => undefined })],
  useCopyToSharedMutation: () => [async () => ({ unwrap: async () => undefined })],
  useRenameMutation: () => [async () => ({ unwrap: async () => undefined })],
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useUsersByIdsQuery: () => ({ data: [] }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: () => {} }),
}));
const toast = vi.hoisted(() => ({ showError: vi.fn(), showSuccess: vi.fn() }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => toast }));
vi.mock("../CreateFolderModal/CreateFolderModal.tsx", () => ({ default: () => null }));

const downloadUtils = vi.hoisted(() => ({
  downloadAuthed: vi.fn(),
  downloadManyAsZip: vi.fn(),
  fetchAuthedBlob: vi.fn(),
}));
vi.mock("../../../../../utils/downloadUtils.tsx", () => ({
  downloadAuthed: downloadUtils.downloadAuthed,
  downloadManyAsZip: downloadUtils.downloadManyAsZip,
  fetchAuthedBlob: downloadUtils.fetchAuthedBlob,
}));

import FilesystemWorkspace from "./FilesystemWorkspace";

let container: HTMLDivElement;
let root: Root;

function render(props: { root: string; rootLabel: string; canWrite?: boolean; onNavigateAboveRoot?: () => void }) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<FilesystemWorkspace {...props} />);
  });
}

function backButton(): HTMLButtonElement {
  const button = container.querySelector('button[aria-label="rework.resources.action.back"]');
  if (!button) throw new Error("back button not rendered");
  return button as HTMLButtonElement;
}

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
  if (!button) throw new Error(`"${name}" not rendered`);
  return button as HTMLButtonElement;
}

describe("FilesystemWorkspace write-action gating", () => {
  it("shows upload/new-folder on a writable root (e.g. Mon espace, default canWrite)", () => {
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.newSubfolder"]')).not.toBeNull();
  });

  it("hides upload/new-folder on Espace d'équipe when canWrite is false", () => {
    render({ root: "teams/nb/shared", rootLabel: "Espace d'équipe", canWrite: false });

    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.newSubfolder"]')).toBeNull();
  });

  it("keeps upload/new-folder on Espace d'équipe when canWrite is true", () => {
    render({ root: "teams/nb/shared", rootLabel: "Espace d'équipe", canWrite: true });

    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.newSubfolder"]')).not.toBeNull();
  });
});

describe("FilesystemWorkspace breadcrumb navigation", () => {
  it("navigates to an intermediate breadcrumb segment (parent), not just root or the current folder", () => {
    render({ root: "teams/nb/shared", rootLabel: "Espace d'équipe" });

    click(folderButton("CIR"));
    click(folderButton("Reports")); // now two levels deep, inside Reports (empty)

    // "CIR" here can only be the breadcrumb's own segment: Reports has no
    // child folders, so no CIR folder row exists at this depth.
    click(folderButton("CIR"));

    // Back at CIR: its child folder row ("Reports") is visible again.
    expect(() => folderButton("Reports")).not.toThrow();
  });
});

describe("FilesystemWorkspace toolbar — bulk actions replace create/upload while selecting", () => {
  function rowCheckbox(): HTMLInputElement {
    // [0] is the header's "select all"; [1] is the one data row in this fixture.
    const boxes = [...container.querySelectorAll('input[type="checkbox"]')];
    const box = boxes[1];
    if (!box) throw new Error("row checkbox not rendered");
    return box as HTMLInputElement;
  }

  it("hides new-folder/add-file and shows the bulk-delete action once a row is selected", () => {
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.newSubfolder"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).toBeNull();

    act(() => {
      rowCheckbox().click();
    });

    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.newSubfolder"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).not.toBeNull();
  });

  it("restores new-folder/add-file once the selection is cleared", () => {
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    act(() => {
      rowCheckbox().click();
    });
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).not.toBeNull();

    act(() => {
      rowCheckbox().click(); // untoggle
    });

    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.newSubfolder"]')).not.toBeNull();
  });

  it("clears the selection and restores new-folder/add-file when the bar's own clear button is clicked", () => {
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    act(() => {
      rowCheckbox().click();
    });
    const clearButton = container.querySelector('button[aria-label="rework.resources.bulkActions.clearSelection"]');
    expect(clearButton).not.toBeNull();

    click(clearButton);

    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.delete"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.action.addFile"]')).not.toBeNull();
    expect(rowCheckbox().checked).toBe(false);
  });

  it("zips the selected file(s) when the bulk download button is clicked", () => {
    downloadUtils.downloadManyAsZip.mockClear();
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    act(() => {
      rowCheckbox().click();
    });
    click(container.querySelector('button[aria-label="rework.resources.bulkActions.download"]'));

    expect(downloadUtils.downloadManyAsZip).toHaveBeenCalledOnce();
    const [files, zipFilename] = downloadUtils.downloadManyAsZip.mock.calls[0];
    expect(files).toHaveLength(1);
    expect(files[0].filename).toBe("notes.txt");
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
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    act(() => {
      rowCheckbox().click();
    });
    const downloadButton = () =>
      container.querySelector('button[aria-label="rework.resources.bulkActions.download"]') as HTMLButtonElement;
    click(downloadButton());

    // Still mid-flight — the zip build hasn't resolved yet.
    expect(downloadButton().disabled).toBe(true);
    expect(downloadButton().getAttribute("aria-busy")).toBe("true");

    await act(async () => {
      resolveDownload();
      await Promise.resolve();
    });

    expect(downloadButton().disabled).toBe(false);
    expect(downloadButton().getAttribute("aria-busy")).toBe("false");
  });

  it("shows an error toast and clears the loading state when the zip download fails", async () => {
    toast.showError.mockClear();
    downloadUtils.downloadManyAsZip.mockRejectedValueOnce(new Error("network down"));
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    act(() => {
      rowCheckbox().click();
    });
    const downloadButton = () =>
      container.querySelector('button[aria-label="rework.resources.bulkActions.download"]') as HTMLButtonElement;
    click(downloadButton());

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(toast.showError).toHaveBeenCalledOnce();
    expect(downloadButton().disabled).toBe(false);
    expect(downloadButton().getAttribute("aria-busy")).toBe("false");
  });

  it("hides the bulk download button when only folders are selected", () => {
    render({ root: "teams/nb/shared", rootLabel: "Espace d'équipe" });

    act(() => {
      rowCheckbox().click(); // "CIR", a directory in this fixture
    });

    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.download"]')).toBeNull();
  });
});

/** Opens a row's "more" menu (portaled into document.body) and clicks the
 *  item whose label key contains `labelKeySuffix`. Assumes exactly one
 *  "more" trigger is rendered (the fixtures below have a single row). */
function clickMoreMenuItem(labelKeySuffix: string) {
  const moreButton = container.querySelector('button[aria-label="rework.resources.action.more"]');
  if (!moreButton) throw new Error("more-menu trigger not rendered");
  click(moreButton);

  const items = [...document.querySelectorAll('[role="presentation"] li, [role="presentation"] button')];
  const item = items.find((el) => el.textContent?.includes(labelKeySuffix));
  if (!item) throw new Error(`menu item containing "${labelKeySuffix}" not found`);
  click(item);
}

describe("FilesystemWorkspace — per-row download (more menu, just under Renommer)", () => {
  it("downloads that file when 'Download' is selected from the more menu", () => {
    downloadUtils.downloadAuthed.mockClear();
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    clickMoreMenuItem("rework.resources.action.download");

    expect(downloadUtils.downloadAuthed).toHaveBeenCalledOnce();
    expect(downloadUtils.downloadAuthed).toHaveBeenCalledWith(expect.stringContaining("notes.txt"), "notes.txt");
  });

  it("lists Download right after Rename when canWrite is true", () => {
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace", canWrite: true });

    const moreButton = container.querySelector('button[aria-label="rework.resources.action.more"]');
    click(moreButton);

    const items = [...document.querySelectorAll('[role="presentation"] li')];
    const labels = items.map((el) => el.textContent ?? "");
    const renameIndex = labels.findIndex((label) => label.includes("rework.resources.action.rename"));
    const downloadIndex = labels.findIndex((label) => label.includes("rework.resources.action.download"));

    expect(renameIndex).toBeGreaterThanOrEqual(0);
    expect(downloadIndex).toBe(renameIndex + 1);
  });

  it("still offers Download on a read-only file row, even though Rename is hidden (canWrite false)", () => {
    downloadUtils.downloadAuthed.mockClear();
    // Reuse the "Mon espace" file fixture but force canWrite=false to prove
    // download survives even when every mutating action is stripped out.
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace", canWrite: false });

    const moreButton = container.querySelector('button[aria-label="rework.resources.action.more"]');
    click(moreButton);
    const items = [...document.querySelectorAll('[role="presentation"] li')];
    const labels = items.map((el) => el.textContent ?? "");

    expect(labels.some((label) => label.includes("rework.resources.action.download"))).toBe(true);
    expect(labels.some((label) => label.includes("rework.resources.action.rename"))).toBe(false);
  });
});

describe("FilesystemWorkspace onNavigateAboveRoot", () => {
  it("is disabled at root when omitted (existing behavior)", () => {
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace" });

    expect(backButton().disabled).toBe(true);
  });

  it("is called by the back button at root when provided", () => {
    const onNavigateAboveRoot = vi.fn();
    render({ root: "teams/nb/users/alice", rootLabel: "Mon espace", onNavigateAboveRoot });

    expect(backButton().disabled).toBe(false);
    click(backButton());
    expect(onNavigateAboveRoot).toHaveBeenCalledOnce();
  });

  it("is not called once navigated below root — the back button pops history first", () => {
    const onNavigateAboveRoot = vi.fn();
    render({ root: "teams/nb/shared", rootLabel: "Espace d'équipe", onNavigateAboveRoot });

    click(folderButton("CIR"));
    click(backButton());

    expect(onNavigateAboveRoot).not.toHaveBeenCalled();
    expect(() => folderButton("CIR")).not.toThrow();
  });
});
