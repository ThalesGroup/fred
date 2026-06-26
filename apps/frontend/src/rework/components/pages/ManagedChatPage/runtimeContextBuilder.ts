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

import type { SearchPolicyName } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { RuntimeContext } from "../../../../slices/runtime/runtimeOpenApi";

type RagScope = "corpus_only" | "hybrid" | "general_only";

/**
 * Build the managed-chat retrieval context from the current composer state.
 *
 * Why this exists:
 * - the send wire should remain small, typed, and easy to test without mounting the hook
 * - document selection hardening needs one explicit place that decides when to send null vs arrays
 *
 * How to use:
 * - pass the current selected libraries/documents and search settings
 * - forward the returned object directly to `send(...)`
 */
export function buildComposerRuntimeContext(params: {
  selectedLibraryIds: string[];
  selectedDocumentUids: string[];
  searchPolicy: SearchPolicyName;
  ragScope: RagScope;
  boundLibraryIds?: string[] | null;
  attachmentsMarkdown?: string | null;
}): Pick<
  RuntimeContext,
  | "selected_document_libraries_ids"
  | "selected_document_uids"
  | "search_policy"
  | "search_rag_scope"
  | "attachments_markdown"
> {
  const selectedDocumentLibrariesIds =
    params.boundLibraryIds && params.boundLibraryIds.length > 0
      ? params.boundLibraryIds
      : params.selectedLibraryIds.length > 0
        ? params.selectedLibraryIds
        : null;
  return {
    selected_document_libraries_ids: selectedDocumentLibrariesIds,
    selected_document_uids: params.selectedDocumentUids.length > 0 ? params.selectedDocumentUids : null,
    search_policy: params.searchPolicy,
    search_rag_scope: params.ragScope,
    ...(params.attachmentsMarkdown != null ? { attachments_markdown: params.attachmentsMarkdown } : {}),
  };
}
