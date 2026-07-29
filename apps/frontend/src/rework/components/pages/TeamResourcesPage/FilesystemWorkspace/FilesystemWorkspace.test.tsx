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
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));
vi.mock("../CreateFolderModal/CreateFolderModal.tsx", () => ({ default: () => null }));

import FilesystemWorkspace from "./FilesystemWorkspace";

let container: HTMLDivElement;
let root: Root;

function render(props: { root: string; rootLabel: string; canWrite?: boolean }) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<FilesystemWorkspace {...props} />);
  });
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
