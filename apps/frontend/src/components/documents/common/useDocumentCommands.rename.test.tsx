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

// Regression coverage for #2407: renaming a document from the Resources tab
// hit the backend correctly but the row kept showing the old name, because
// renameDocument called refresh() with no tag id - and DocumentWorkspace's
// refetchDocs callback is a no-op without one, so the folder page was never
// reloaded. renameDocument must forward the caller's tag id, the way
// removeFromLibrary already does.
//
// Second case: a failed rename must surface a toast, must NOT reload the
// folder page, and must rethrow - RenameModal relies on the rejection to keep
// itself open with the typed name still in the input.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const renameMutation = vi.fn();
const refetchTags = vi.fn(async () => undefined);
const refetchDocs = vi.fn(async (_tagId?: string) => undefined);
const showError = vi.fn();
const showSuccess = vi.fn();
const showInfo = vi.fn();

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess, showError, showInfo }),
}));
vi.mock("../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useRenameDocumentKnowledgeFlowV1DocumentMetadataDocumentUidNamePutMutation: () => [renameMutation],
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation: () => [vi.fn()],
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [vi.fn()],
  useMutateDocumentLabelsMutation: () => [vi.fn()],
}));
vi.mock("../../../slices/knowledgeFlow/knowledgeFlowApi.blob", () => ({
  useLazyDownloadRawContentBlobQuery: () => [vi.fn()],
}));

import { useDocumentCommands } from "./useDocumentCommands";

const doc = {
  identity: { document_uid: "uid-1", document_name: "report.pdf", title: null },
  source: { retrievable: true },
} as unknown as DocumentMetadata;

function Harness({ onRender }: { onRender: (commands: ReturnType<typeof useDocumentCommands>) => void }) {
  onRender(useDocumentCommands({ refetchTags, refetchDocs }));
  return null;
}

describe("useDocumentCommands.renameDocument (#2407)", () => {
  let container: HTMLDivElement;
  let root: Root;
  let commands: ReturnType<typeof useDocumentCommands>;

  beforeEach(() => {
    renameMutation.mockReset();
    refetchTags.mockClear();
    refetchDocs.mockClear();
    showError.mockClear();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<Harness onRender={(c) => (commands = c)} />);
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("reloads the caller's folder page after the rename succeeds", async () => {
    renameMutation.mockReturnValue({ unwrap: async () => undefined });

    await act(async () => {
      await commands.renameDocument(doc, "Q3-Final.pdf", "tag-1");
    });

    expect(renameMutation).toHaveBeenCalledWith({
      documentUid: "uid-1",
      bodyRenameDocumentKnowledgeFlowV1DocumentMetadataDocumentUidNamePut: { name: "Q3-Final.pdf" },
    });
    // The whole point of the fix: the tag id reaches refetchDocs, so the
    // folder page reloads and the row picks up its new name.
    expect(refetchDocs).toHaveBeenCalledWith("tag-1");
    expect(refetchTags).toHaveBeenCalledTimes(1);
  });

  it("toasts, skips the reload and rethrows when the rename fails", async () => {
    renameMutation.mockReturnValue({
      unwrap: async () => {
        throw { data: { detail: "name already taken" } };
      },
    });

    await act(async () => {
      await expect(commands.renameDocument(doc, "Q3-Final.pdf", "tag-1")).rejects.toBeDefined();
    });

    expect(showError).toHaveBeenCalledWith(expect.objectContaining({ detail: "name already taken" }));
    expect(refetchDocs).not.toHaveBeenCalled();
  });
});
