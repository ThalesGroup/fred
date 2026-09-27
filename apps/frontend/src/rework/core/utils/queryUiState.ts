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

export type QueryUiState = "loading" | "error" | "ready";

interface QueryUiStateInput {
  isLoading?: boolean;
  isFetching?: boolean;
  isUninitialized?: boolean;
  isError?: boolean;
}

interface QueryUiStateOptions {
  /**
   * Treat a refetch that already has data as "ready" rather than "loading".
   *
   * Pass this wherever the state gates the page's whole body: with the default,
   * a background revalidation replaces the page with a spinner and unmounts
   * everything under it, losing whatever state those children held — and, since
   * their own queries then have no subscribers, dropping their cache entries
   * too. Leave it off where the state drives an inline indicator, which is what
   * the default was written for.
   */
  keepPreviousWhileRefetching?: boolean;
}

/**
 * Resolve a stable UI state from RTK Query lifecycle flags.
 *
 * Why this exists:
 * - route transitions can briefly expose stale `isError` while a refetch is running
 * - pages should consistently render Loading first, then either Error or Ready
 */
export function getQueryUiState(
  { isLoading, isFetching, isUninitialized, isError }: QueryUiStateInput,
  { keepPreviousWhileRefetching = false }: QueryUiStateOptions = {},
): QueryUiState {
  // `isLoading` is RTK Query's "fetching with nothing to show yet"; `isFetching`
  // stays true for every later revalidation as well.
  const pending = keepPreviousWhileRefetching
    ? isLoading || isUninitialized
    : isLoading || isFetching || isUninitialized;
  if (pending) {
    return "loading";
  }
  if (isError) {
    return "error";
  }
  return "ready";
}
