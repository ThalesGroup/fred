import { useListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export function useDocumentSources() {
  const { data, error, isLoading, refetch } = useListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetQuery();

  return {
    sources: data ?? [],
    isLoading,
    error,
    refetch,
  };
}
