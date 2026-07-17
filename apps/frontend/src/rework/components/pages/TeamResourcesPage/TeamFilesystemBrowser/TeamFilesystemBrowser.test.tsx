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

// Regression coverage for issue #1996 point A.1: a Member without
// CAN_UPDATE_RESOURCES must not see write actions (upload / new folder /
// delete) on the "Espace d'équipe" root, but must keep them on their own
// "Mon espace" root (ownership-only, no role gate — see
// ScopedAreaFilesystem docstring). `t` echoes its key so we can assert on
// which aria-labels render.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => undefined }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useLsQuery: () => ({
    data: [
      { path: "Folder1", type: "directory" },
      { path: "notes.txt", type: "file" },
    ],
    refetch: () => {},
  }),
  useDeleteFileMutation: () => [async () => ({ unwrap: async () => undefined }), { isLoading: false }],
  useMkdirMutation: () => [async () => ({ unwrap: async () => undefined })],
  useUploadFileMutation: () => [async () => ({ unwrap: async () => undefined })],
  useCopyToSharedMutation: () => [async () => ({ unwrap: async () => undefined })],
}));
vi.mock("../../../../../components/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: () => {} }),
}));
vi.mock("../CreateFolderModal/CreateFolderModal.tsx", () => ({ default: () => null }));

import TeamFilesystemBrowser from "./TeamFilesystemBrowser";

function render(props: { root: string; canWrite?: boolean }): string {
  return renderToStaticMarkup(<TeamFilesystemBrowser {...props} />);
}

describe("TeamFilesystemBrowser write-action gating", () => {
  it("shows upload/new-folder/delete on a writable root (e.g. Mon espace, default canWrite)", () => {
    const html = render({ root: "teams/nb/users/alice" });

    expect(html).toContain('aria-label="rework.resources.action.addFile"');
    expect(html).toContain('aria-label="rework.resources.action.newSubfolder"');
    expect(html).toContain('aria-label="rework.resources.action.delete"');
    // The file row's "…" overflow menu is offered too (carries the delete action).
    expect(html).toContain('aria-label="rework.resources.action.more"');
  });

  it("hides upload/new-folder/delete on Espace d'équipe when canWrite is false", () => {
    const html = render({ root: "teams/nb/shared", canWrite: false });

    expect(html).not.toContain('aria-label="rework.resources.action.addFile"');
    expect(html).not.toContain('aria-label="rework.resources.action.newSubfolder"');
    expect(html).not.toContain('aria-label="rework.resources.action.delete"');
    // No write action survives for the file row either, so the "…" menu itself
    // (which only ever carries delete for a non-shareable root) is not rendered.
    expect(html).not.toContain('aria-label="rework.resources.action.more"');
  });

  it("keeps upload/new-folder/delete on Espace d'équipe when canWrite is true", () => {
    const html = render({ root: "teams/nb/shared", canWrite: true });

    expect(html).toContain('aria-label="rework.resources.action.addFile"');
    expect(html).toContain('aria-label="rework.resources.action.newSubfolder"');
    expect(html).toContain('aria-label="rework.resources.action.delete"');
  });
});
