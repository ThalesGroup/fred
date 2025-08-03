import { useListTagsKnowledgeFlowV1TagsGetQuery, TagWithItemsId } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export function useLibraries(type: "library" = "library") {
  const { data, error, isLoading, refetch } = useListTagsKnowledgeFlowV1TagsGetQuery();

  const tags: TagWithItemsId[] = (data ?? []).filter((tag) => tag.type === type);

  return {
    tags,
    isLoading,
    error,
    refetch,
  };
}
