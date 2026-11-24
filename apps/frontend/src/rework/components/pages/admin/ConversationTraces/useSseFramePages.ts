// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import type { store } from "../../../../../common/store";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  GetConversationTraceSseFramePageApiArg,
  TraceSseFramePage,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const concurrentPages = 4;
export type SsePageRequest = GetConversationTraceSseFramePageApiArg;

export function useSseFramePages(requests: SsePageRequest[]) {
  const dispatch = useDispatch<typeof store.dispatch>();
  const [loaded, setLoaded] = useState<{
    requests: SsePageRequest[];
    pages: Map<string, TraceSseFramePage[]>;
    hasError: boolean;
  }>();

  useEffect(() => {
    if (!requests.length) return;
    let cancelled = false;
    const endpoint = enhancedControlPlaneApi.endpoints.getConversationTraceSseFramePage;

    async function load() {
      const pages = new Map<string, TraceSseFramePage[]>();
      let hasError = false;
      for (let start = 0; start < requests.length && !cancelled; start += concurrentPages) {
        const batch = requests.slice(start, start + concurrentPages);
        // Keep the results subscribed until read, including deduplicated in-flight requests.
        const pending = batch.map((request) => dispatch(endpoint.initiate(request, { forceRefetch: true })));
        const results = await Promise.all(pending).finally(() => pending.forEach((query) => query.unsubscribe()));
        if (cancelled) return;
        const accessDenied = results.some(({ error }) => {
          if (!error || !("status" in error)) return false;
          const status = error.status === "PARSING_ERROR" ? error.originalStatus : error.status;
          return status === 401 || status === 403;
        });
        if (accessDenied) {
          // Consent may have changed after earlier pages were authorized.
          setLoaded({ requests, pages: new Map(), hasError: true });
          return;
        }
        for (const [index, result] of results.entries()) {
          if (!result.isSuccess || !result.data) {
            hasError = true;
            continue;
          }
          const { ref } = batch[index];
          const lane = pages.get(ref);
          if (lane) lane.push(result.data);
          else pages.set(ref, [result.data]);
        }
      }
      if (!cancelled) setLoaded({ requests, pages, hasError });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [dispatch, requests]);

  const current = loaded?.requests === requests ? loaded : undefined;
  // Drop the previous protected index when the requested evidence changes.
  if (loaded && !current) setLoaded(undefined);
  return { pages: current?.pages, hasError: current?.hasError, isLoading: requests.length > 0 && !current };
}
