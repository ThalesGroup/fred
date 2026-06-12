import { describe, expect, it } from "vitest";
import {
  buildLibrarySelectionKey,
  parseLibrarySelectionKey,
  reconcileSelectedDocumentUids,
  resolveDocumentScopeState,
} from "./documentSelection";

describe("buildLibrarySelectionKey", () => {
  it("returns an empty key for no libraries", () => {
    expect(buildLibrarySelectionKey([])).toBe("");
  });

  it("returns one stable pipe-delimited key", () => {
    expect(buildLibrarySelectionKey(["lib-b", "lib-a", "lib-b"])).toBe("lib-a|lib-b");
  });
});

describe("parseLibrarySelectionKey", () => {
  it("returns an empty list for the empty key", () => {
    expect(parseLibrarySelectionKey("")).toEqual([]);
  });

  it("reconstructs the ordered library ids", () => {
    expect(parseLibrarySelectionKey("lib-a|lib-b")).toEqual(["lib-a", "lib-b"]);
  });
});

describe("reconcileSelectedDocumentUids", () => {
  it("keeps selected documents that are still available", () => {
    expect(reconcileSelectedDocumentUids(["doc-1", "doc-2"], ["doc-2", "doc-1", "doc-3"])).toEqual(["doc-1", "doc-2"]);
  });

  it("drops selected documents that are no longer available", () => {
    expect(reconcileSelectedDocumentUids(["doc-1", "doc-2"], ["doc-2"])).toEqual(["doc-2"]);
  });

  it("preserves the existing empty selection instance when nothing is selected", () => {
    const selected: string[] = [];
    expect(reconcileSelectedDocumentUids(selected, ["doc-1"])).toBe(selected);
  });
});

describe("resolveDocumentScopeState", () => {
  it("asks the user to select a library when the picker is visible but empty", () => {
    expect(
      resolveDocumentScopeState({
        showLibraries: true,
        showDocuments: true,
        effectiveLibraryIds: [],
      }),
    ).toEqual({
      hasDocumentScope: false,
      showSelectLibraryFirst: true,
      showDocumentConfigurationWarning: false,
    });
  });

  it("shows a configuration warning when documents are enabled without any library path", () => {
    expect(
      resolveDocumentScopeState({
        showLibraries: false,
        showDocuments: true,
        effectiveLibraryIds: [],
      }),
    ).toEqual({
      hasDocumentScope: false,
      showSelectLibraryFirst: false,
      showDocumentConfigurationWarning: true,
    });
  });

  it("treats a non-empty library scope as ready for document browsing", () => {
    expect(
      resolveDocumentScopeState({
        showLibraries: true,
        showDocuments: true,
        effectiveLibraryIds: ["lib-a"],
      }),
    ).toEqual({
      hasDocumentScope: true,
      showSelectLibraryFirst: false,
      showDocumentConfigurationWarning: false,
    });
  });
});
