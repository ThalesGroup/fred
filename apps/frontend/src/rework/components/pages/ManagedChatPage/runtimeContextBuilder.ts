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
