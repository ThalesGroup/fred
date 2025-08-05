import {
  TagType,
  // fetch all the tags possibly filtered by tag type as done here
  useListAllTagsKnowledgeFlowV1TagsGetQuery
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

/**
 * Custom hook to fetch all document tag libraries (i.e., tags of type "document").
 *
 * It uses the `useListAllTagsKnowledgeFlowV1TagsGetQuery` backend endpoint with `type = "document"`,
 * and returns the tags along with loading and error states.
 *
 * @returns An object containing:
 *  - `tags`: The list of document libraries (`TagWithItemsId[]`)
 *  - `isLoading`: Whether the request is in flight
 *  - `error`: Any encountered error
 *  - `refetch`: A method to manually refetch the tags
 */
export function useDocumentTags() {
  const { data, error, isLoading, refetch } =
    useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" as TagType});

  return {
    tags: data ?? [],
    isLoading,
    error,
    refetch,
  };
}