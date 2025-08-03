import { useGetDocumentSourcesQuery } from "../slices/documentApi";

export function useDocumentSources() {
  const { data, error, isLoading, refetch } = useGetDocumentSourcesQuery();

  return {
    sources: data ?? [],
    isLoading,
    error,
    refetch,
  };
}
