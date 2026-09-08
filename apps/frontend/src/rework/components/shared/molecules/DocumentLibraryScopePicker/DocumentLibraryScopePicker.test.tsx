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

// A scope is libraries + documents, unioned - there is no "everything here
// except this" to send. These cases pin how the picker still lets a user say
// it: a folder shows its documents ticked, and unticking one expands the folder
// into its own documents minus that one.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const TAG = {
  id: "tag-1",
  name: "logs",
  path: "",
  type: "document",
  item_ids: ["doc-1", "doc-2", "doc-3"],
};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ activeTeam: { id: "team-1" } }),
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  TagType: { document: "document" },
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({ data: [TAG], isLoading: false }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({
      unwrap: async () => ({
        documents: TAG.item_ids.map((uid) => ({
          identity: { document_uid: uid, document_name: `${uid}.txt` },
          file: { file_type: "txt" },
        })),
      }),
    }),
  ],
}));

import { DocumentLibraryScopePicker } from "./DocumentLibraryScopePicker";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

/** Render, then expand the single folder so its documents are listed. */
async function renderExpanded(props: Parameters<typeof DocumentLibraryScopePicker>[0]) {
  await act(async () => {
    root.render(<DocumentLibraryScopePicker {...props} />);
  });
  const expand = container.querySelector("button");
  await act(async () => {
    expand?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

/** Document checkboxes, in render order — the folder's own checkbox comes first. */
function checkboxes(): HTMLInputElement[] {
  return Array.from(container.querySelectorAll<HTMLInputElement>("input[type=checkbox]"));
}

describe("DocumentLibraryScopePicker folder selection", () => {
  it("shows a picked folder's documents as selected", async () => {
    await renderExpanded({
      selectedTagIds: ["tag-1"],
      onChange: () => {},
      selectedDocumentUids: [],
      onDocumentsChange: () => {},
    });

    const [folder, ...docs] = checkboxes();
    expect(folder.checked).toBe(true);
    expect(docs).toHaveLength(3);
    expect(docs.every((box) => box.checked)).toBe(true);
  });

  it("expands the folder into its other documents when one is unticked", async () => {
    const onChange = vi.fn();
    const onDocumentsChange = vi.fn();
    await renderExpanded({
      selectedTagIds: ["tag-1"],
      onChange,
      selectedDocumentUids: [],
      onDocumentsChange,
    });

    const [, firstDoc] = checkboxes();
    await act(async () => {
      firstDoc.click();
    });

    // The folder can no longer speak for the selection, so it steps aside.
    expect(onChange).toHaveBeenCalledWith([]);
    expect(onDocumentsChange).toHaveBeenCalledWith(["doc-2", "doc-3"]);
  });

  it("drops the per-document entries a folder pick makes redundant", async () => {
    const onDocumentsChange = vi.fn();
    await renderExpanded({
      selectedTagIds: [],
      onChange: () => {},
      selectedDocumentUids: ["doc-2", "other-doc"],
      onDocumentsChange,
    });

    const [folder] = checkboxes();
    await act(async () => {
      folder.click();
    });

    expect(onDocumentsChange).toHaveBeenCalledWith(["other-doc"]);
  });

  it("keeps a pinned library scope untouchable from a document row", async () => {
    const onChange = vi.fn();
    await renderExpanded({
      selectedTagIds: ["tag-1"],
      onChange,
      selectedDocumentUids: [],
      onDocumentsChange: () => {},
      disableLibrarySelection: true,
    });

    const [, firstDoc] = checkboxes();
    expect(firstDoc.disabled).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
  });
});
