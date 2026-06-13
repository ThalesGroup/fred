import { describe, expect, it } from "vitest";
import { buildComposerRuntimeContext } from "./runtimeContextBuilder";

describe("buildComposerRuntimeContext", () => {
  it("sends selected document uids when documents are chosen", () => {
    expect(
      buildComposerRuntimeContext({
        selectedLibraryIds: ["lib-1"],
        selectedDocumentUids: ["doc-1", "doc-2"],
        searchPolicy: "hybrid",
        ragScope: "hybrid",
      }),
    ).toEqual({
      selected_document_libraries_ids: ["lib-1"],
      selected_document_uids: ["doc-1", "doc-2"],
      search_policy: "hybrid",
      search_rag_scope: "hybrid",
    });
  });

  it("keeps the existing library-only behavior when no documents are selected", () => {
    expect(
      buildComposerRuntimeContext({
        selectedLibraryIds: ["lib-1"],
        selectedDocumentUids: [],
        searchPolicy: "semantic",
        ragScope: "corpus_only",
      }),
    ).toEqual({
      selected_document_libraries_ids: ["lib-1"],
      selected_document_uids: null,
      search_policy: "semantic",
      search_rag_scope: "corpus_only",
    });
  });
});
