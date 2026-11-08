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

import { useCallback, useEffect, useMemo, useState } from "react";
import { useDispatch } from "react-redux";
import type { store } from "../../../../../common/store";
import {
  enhancedControlPlaneApi as api,
  useMySpacesQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { type SearchSources, unifyPrompts } from "./homeSearchIndex";

const EMPTY: SearchSources = { agents: [], teams: [], prompts: [] };

/** Home uses the same complete, authorized catalogs as resource management.
 * Four spaces at a time, one minute and 10,000 resources overall; a failed traversal is never shown
 * as a complete index. A denied scope contributes no resource data. */
export function useHomeSearchIndex(active: boolean) {
  const context = useMySpacesQuery(undefined, { skip: !active, refetchOnMountOrArgChange: true });
  const dispatch = useDispatch<typeof store.dispatch>();
  const [refresh, setRefresh] = useState(0);
  const spaces = context.currentData;
  // Structural sharing keeps `spaces` through a refresh that changes nothing: no reindex.
  const scope = useMemo(() => ({ spaces, active, refresh }), [spaces, active, refresh]);
  const [snapshot, setSnapshot] = useState<{ scope: typeof scope; sources: SearchSources; failed: boolean }>();

  useEffect(() => {
    if (!active || !spaces || context.isError) return;
    let cancelled = false;
    let nextSpace = 0;
    let failed = false;
    const pending = new Set<{ abort: () => void; unsubscribe: () => void }>();
    const sources: SearchSources = {
      agents: [],
      teams: [],
      prompts: [],
    };
    const stop = () => {
      for (const request of pending) {
        request.abort();
        request.unsubscribe();
      }
    };
    const timeout = setTimeout(() => {
      cancelled = true;
      stop();
      setSnapshot({ scope, sources: EMPTY, failed: true });
    }, 60_000);
    const worker = async () => {
      while (!cancelled && nextSpace < spaces.length) {
        const space = spaces[nextSpace++];
        // Prompt catalogs support all spaces; agent routes retain their own scope.
        const agents =
          space.kind === "team" || space.kind === "personal"
            ? dispatch(api.endpoints.listAgentInstances.initiate({ spaceId: space.id }, { forceRefetch: true }))
            : undefined;
        if (agents) sources.teams.push({ id: space.id, name: space.name });
        const prompts = dispatch(api.endpoints.listPrompts.initiate({ spaceId: space.id }, { forceRefetch: true }));
        if (agents) pending.add(agents);
        pending.add(prompts);
        const results = await Promise.all([agents, prompts]);
        for (const result of results) {
          if (
            result?.error &&
            !("status" in result.error && (result.error.status === 403 || result.error.status === 404))
          )
            failed = true;
        }
        if (!cancelled) {
          for (const instance of (results[0]?.isSuccess && results[0].data?.items) || []) {
            if (instance.status === "enabled")
              sources.agents.push({ instance, teamId: space.id, teamName: space.name });
          }
          sources.prompts.push(
            ...unifyPrompts([
              { spaceName: space.name, prompts: (results[1].isSuccess && results[1].data?.items) || [] },
            ]),
          );
          if (sources.agents.length + sources.prompts.length > 10_000) {
            cancelled = true;
            stop();
            setSnapshot({ scope, sources: EMPTY, failed: true });
          }
        }
        agents?.unsubscribe();
        prompts.unsubscribe();
        if (agents) pending.delete(agents);
        pending.delete(prompts);
      }
    };
    void Promise.all(Array.from({ length: Math.min(4, spaces.length) }, worker)).then(() => {
      clearTimeout(timeout);
      if (!cancelled) setSnapshot({ scope, sources: failed ? EMPTY : sources, failed });
    });
    return () => {
      cancelled = true;
      clearTimeout(timeout);
      stop();
    };
  }, [active, context.isError, dispatch, scope, spaces]);

  const current = snapshot?.scope === scope && !context.isError ? snapshot : undefined;
  const retry = useCallback(() => {
    if (context.isError) void context.refetch();
    else setRefresh((value) => value + 1);
  }, [context.isError, context.refetch]);
  return {
    ...(current?.sources ?? EMPTY),
    scope,
    isLoading: active && !context.isError && !current,
    isError: context.isError || Boolean(current?.failed),
    retry,
  };
}
