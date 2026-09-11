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

// Regression coverage: removing a document from a nested folder moved the
// folder back to the root of the corpus tree. Both remove commands rebuild the
// tag payload from scratch and used to leave `path` out, which was harmless
// until the tag update endpoint started applying every field of the body - a
// missing path then became null. The current path must travel with the new
// item_ids.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentMetadata, TagWithItemsId } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const updateTagMutation = vi.fn();
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

const docOne = {
  identity: { document_uid: "uid-1", document_name: "report.pdf", title: null },
  source: { retrievable: true },
} as unknown as DocumentMetadata;

const docTwo = {
  identity: { document_uid: "uid-2", document_name: "annex.pdf", title: null },
  source: { retrievable: true },
} as unknown as DocumentMetadata;

const tag = {
  id: "tag-1",
  name: "Reports",
  path: "Finance/2026",
  description: "d",
  type: "document",
  item_ids: ["uid-1", "uid-2"],
} as unknown as TagWithItemsId;

function Harness({ onRender }: { onRender: (commands: ReturnType<typeof useDocumentCommands>) => void }) {
  onRender(useDocumentCommands({ refetchTags, refetchDocs }));
  return null;
}

describe("useDocumentCommands remove keeps the folder path", () => {
  let container: HTMLDivElement;
  let root: Root;
  let commands: ReturnType<typeof useDocumentCommands>;

  beforeEach(() => {
    updateTagMutation.mockReset();
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

  it("sends the current path when removing a single document", async () => {
    updateTagMutation.mockReturnValue({ unwrap: async () => undefined });

    await act(async () => {
      await commands.removeFromLibrary(docOne, tag);
    });

    expect(updateTagMutation).toHaveBeenCalledWith({
      tagId: "tag-1",
      tagUpdate: {
        name: "Reports",
        path: "Finance/2026",
        description: "d",
        type: "document",
        item_ids: ["uid-2"],
      },
    });
    expect(refetchDocs).toHaveBeenCalledWith("tag-1");
  });

  it("sends the current path when removing documents in bulk", async () => {
    updateTagMutation.mockReturnValue({ unwrap: async () => undefined });

    await act(async () => {
      await commands.bulkRemoveFromLibraryForTag([docOne, docTwo], tag);
    });

    expect(updateTagMutation).toHaveBeenCalledWith({
      tagId: "tag-1",
      tagUpdate: {
        name: "Reports",
        path: "Finance/2026",
        description: "d",
        type: "document",
        item_ids: [],
      },
    });
    expect(refetchDocs).toHaveBeenCalledWith("tag-1");
  });
});
