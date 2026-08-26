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

import { useEffect, useMemo, useState } from "react";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import { useLazyTeamAgentInstancesQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  type ManagedAgentInstanceSummary,
  type PromptSummary,
  useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery,
  useLazyGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { type SearchSources, unifyPrompts } from "./homeSearchIndex.ts";

/**
 * Aggregates the searchable universe for the Home Spotlight — there is no global
 * search endpoint, so it fans out per team (member teams from bootstrap). All
 * fetching is lazy and gated on `active` (the search field's first focus), so a
 * user who never opens the search pays nothing; results accumulate into state as
 * each team resolves and are reused from the RTK cache on later opens.
 *
 * Cost is 2N+1 requests on first open (N = member teams): agent instances +
 * prompts per team, plus the published marketplace prompts. Acceptable for a v1
 * launcher; a dedicated cross-team search endpoint would replace this later.
 */
export function useHomeSearchIndex(active: boolean): SearchSources {
  const { availableTeams } = useFrontendBootstrap();

  const teamMeta = useMemo(
    () => availableTeams.filter((team) => team.is_member).map((team) => ({ id: team.id, name: team.name })),
    [availableTeams],
  );

  const [fetchAgents] = useLazyTeamAgentInstancesQuery();
  const [fetchPrompts] = useLazyGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery();
  const { data: marketplacePrompts } = useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery(undefined, {
    skip: !active,
  });

  const [agentsByTeam, setAgentsByTeam] = useState<Record<string, ManagedAgentInstanceSummary[]>>({});
  const [promptsByTeam, setPromptsByTeam] = useState<Record<string, PromptSummary[]>>({});

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void Promise.all(
      teamMeta.map(async ({ id }) => {
        // preferCacheValue: reuse a warm cache (TeamAgentsPage / PromptsPage)
        // rather than refetch. Each side degrades to [] on error so one
        // unreachable team never sinks the whole index.
        const [agents, prompts] = await Promise.all([
          fetchAgents({ teamId: id }, true)
            .unwrap()
            .catch(() => [] as ManagedAgentInstanceSummary[]),
          fetchPrompts({ teamId: id }, true)
            .unwrap()
            .catch(() => [] as PromptSummary[]),
        ]);
        return { id, agents, prompts };
      }),
    ).then((entries) => {
      if (cancelled) return;
      setAgentsByTeam((prev) => {
        const next = { ...prev };
        for (const entry of entries) next[entry.id] = entry.agents;
        return next;
      });
      setPromptsByTeam((prev) => {
        const next = { ...prev };
        for (const entry of entries) next[entry.id] = entry.prompts;
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [active, teamMeta, fetchAgents, fetchPrompts]);

  return useMemo<SearchSources>(() => {
    const agents = teamMeta.flatMap(({ id, name }) =>
      (agentsByTeam[id] ?? [])
        // Only usable agents belong in a launcher (mirrors the recent-agents row).
        .filter((instance) => instance.status === "enabled" && !instance.suspension_reason)
        .map((instance) => ({ instance, teamId: id, teamName: name })),
    );
    const teamPromptGroups = teamMeta.map(({ id, name }) => ({
      teamId: id,
      teamName: name,
      prompts: promptsByTeam[id] ?? [],
    }));
    return {
      agents,
      teams: teamMeta,
      prompts: unifyPrompts(teamPromptGroups, marketplacePrompts ?? []),
    };
  }, [teamMeta, agentsByTeam, promptsByTeam, marketplacePrompts]);
}
