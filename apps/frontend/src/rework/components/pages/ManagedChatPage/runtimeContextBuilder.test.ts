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

  it("omits both reasoning keys when the agent offers no picker", () => {
    // Omitted ≠ false: an absent key reaches the runtime as "no choice was
    // made" and leaves levels 1-2 in charge.
    const context = buildComposerRuntimeContext({
      selectedLibraryIds: [],
      selectedDocumentUids: [],
      searchPolicy: "hybrid",
      ragScope: "hybrid",
    });
    expect("reasoning" in context).toBe(false);
    expect("reasoning_effort" in context).toBe(false);
  });

  it('maps "off" to an explicit decline with no effort value', () => {
    // The strip path stays dominant runtime-side: a declined turn must never
    // carry a reasoning_effort, not even "off".
    const context = buildComposerRuntimeContext({
      selectedLibraryIds: [],
      selectedDocumentUids: [],
      searchPolicy: "hybrid",
      ragScope: "hybrid",
      reasoningEffort: "off",
    });
    expect(context.reasoning).toBe(false);
    expect("reasoning_effort" in context).toBe(false);
  });

  it("maps an effort level to reasoning=true plus the level", () => {
    const context = buildComposerRuntimeContext({
      selectedLibraryIds: [],
      selectedDocumentUids: [],
      searchPolicy: "hybrid",
      ragScope: "hybrid",
      reasoningEffort: "low",
    });
    expect(context.reasoning).toBe(true);
    expect(context.reasoning_effort).toBe("low");
  });
});
