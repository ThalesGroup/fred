export type QueryUiState = "loading" | "error" | "ready";

interface QueryUiStateInput {
  isLoading?: boolean;
  isFetching?: boolean;
  isUninitialized?: boolean;
  isError?: boolean;
}

/**
 * Resolve a stable UI state from RTK Query lifecycle flags.
 *
 * Why this exists:
 * - route transitions can briefly expose stale `isError` while a refetch is running
 * - pages should consistently render Loading first, then either Error or Ready
 */
export function getQueryUiState({ isLoading, isFetching, isUninitialized, isError }: QueryUiStateInput): QueryUiState {
  if (isLoading || isFetching || isUninitialized) {
    return "loading";
  }
  if (isError) {
    return "error";
  }
  return "ready";
}
