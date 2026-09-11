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

// Regression coverage: removing a document from a folder used to send a tag
// update without `path`. The backend PUT replaces the whole tag, so the folder
// lost its path and a nested folder "A/B" re-appeared at the root as "B".
// Both the single and the bulk removal must forward `tag.path` verbatim -
// including a null path, which keeps a root folder at the root.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentMetadata, TagUpdate, TagWithItemsId } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const updateTagMutation = vi.fn((_args: { tagId: string; tagUpdate: TagUpdate }) => ({
  unwrap: () => Promise.resolve({}),
}));
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
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation: () => [updateTagMutation],
  useRenameDocumentKnowledgeFlowV1DocumentMetadataDocumentUidNamePutMutation: () => [vi.fn()],
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [vi.fn()],
  useMutateDocumentLabelsMutation: () => [vi.fn()],
}));
vi.mock("../../../slices/knowledgeFlow/knowledgeFlowApi.blob", () => ({
  useLazyDownloadRawContentBlobQuery: () => [vi.fn()],
}));

import { useDocumentCommands } from "./useDocumentCommands";

const docA = {
  identity: { document_uid: "uid-1", document_name: "a.pdf", title: null },
  source: { retrievable: true },
} as unknown as DocumentMetadata;

const docB = {
  identity: { document_uid: "uid-2", document_name: "b.pdf", title: null },
  source: { retrievable: true },
} as unknown as DocumentMetadata;

const nestedTag = {
  id: "tag-1",
  name: "B",
  path: "A",
  type: "document",
  description: null,
  item_ids: ["uid-1", "uid-2"],
} as unknown as TagWithItemsId;

const rootTag = {
  id: "tag-2",
  name: "Root",
  path: null,
  type: "document",
  description: null,
  item_ids: ["uid-1", "uid-2"],
} as unknown as TagWithItemsId;

function Harness({ onRender }: { onRender: (commands: ReturnType<typeof useDocumentCommands>) => void }) {
  onRender(useDocumentCommands({ refetchTags, refetchDocs }));
  return null;
}

describe("useDocumentCommands.removeFromLibrary keeps the folder path", () => {
  let container: HTMLDivElement;
  let root: Root;
  let commands: ReturnType<typeof useDocumentCommands>;

  beforeEach(() => {
    updateTagMutation.mockClear();
    refetchTags.mockClear();
    refetchDocs.mockClear();
    showError.mockClear();
    showSuccess.mockClear();
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

  it("forwards the parent path when removing a single document", async () => {
    await act(async () => {
      await commands.removeFromLibrary(docA, nestedTag);
    });

    expect(updateTagMutation).toHaveBeenCalledTimes(1);
    expect(updateTagMutation).toHaveBeenCalledWith({
      tagId: "tag-1",
      tagUpdate: expect.objectContaining({ name: "B", path: "A", item_ids: ["uid-2"] }),
    });
    expect(refetchTags).toHaveBeenCalledTimes(1);
    expect(refetchDocs).toHaveBeenCalledWith("tag-1");
  });

  it("forwards the parent path when removing several documents at once", async () => {
    await act(async () => {
      await commands.bulkRemoveFromLibraryForTag([docA, docB], {
        ...nestedTag,
        item_ids: ["uid-1", "uid-2", "uid-3"],
      });
    });

    expect(updateTagMutation).toHaveBeenCalledTimes(1);
    expect(updateTagMutation).toHaveBeenCalledWith({
      tagId: "tag-1",
      tagUpdate: expect.objectContaining({ name: "B", path: "A", item_ids: ["uid-3"] }),
    });
    expect(refetchTags).toHaveBeenCalledTimes(1);
    expect(refetchDocs).toHaveBeenCalledWith("tag-1");
  });

  it("sends a null path for a root folder instead of dropping the field", async () => {
    await act(async () => {
      await commands.removeFromLibrary(docA, rootTag);
    });

    const { tagUpdate } = updateTagMutation.mock.calls[0][0];
    expect(tagUpdate).toHaveProperty("path");
    expect(tagUpdate.path).toBeNull();
  });
});
