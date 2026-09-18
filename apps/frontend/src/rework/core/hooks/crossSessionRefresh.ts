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

import { useEffect } from "react";

/**
 * Keeping a query fresh against changes made in another browser session.
 *
 * RTK tag invalidation only reaches the Redux store that issued the mutation,
 * and this app never calls `setupListeners`, so a query whose answer an
 * administrator can change elsewhere — a catalog, an availability check — has
 * to ask for itself: bounded polling plus an explicit focus refetch.
 */
export const CROSS_SESSION_REFRESH_INTERVAL_MS = 60_000;

/** Query options for a subscription that must survive a cross-session change. */
export function crossSessionRefreshOptions(skip: boolean) {
  return {
    skip,
    pollingInterval: skip ? 0 : CROSS_SESSION_REFRESH_INTERVAL_MS,
    refetchOnMountOrArgChange: CROSS_SESSION_REFRESH_INTERVAL_MS / 1000,
  };
}

/** Refetch when the window regains focus, so a revocation lands without a reload. */
export function useRefetchOnWindowFocus(refetch: () => unknown, skip: boolean) {
  useEffect(() => {
    if (skip || typeof window === "undefined") return;
    const onFocus = () => void refetch();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refetch, skip]);
}
