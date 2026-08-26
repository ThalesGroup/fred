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

// Pure index/filter for the Home "Spotlight" search (#2298). Kept free of React
// and RTK so the matching, per-group cap and prompt de-dup are unit-testable in
// isolation; the hook (`useHomeSearchIndex`) only feeds it the aggregated data.

import type {
  ManagedAgentInstanceSummary,
  MarketplacePromptSummary,
  PromptSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";

/** Max results shown per group (Agents / Teams / Prompts). */
export const HOME_SEARCH_GROUP_CAP = 5;

export interface AgentEntry {
  instance: ManagedAgentInstanceSummary;
  teamId: string;
  teamName: string;
}
export interface TeamEntry {
  id: string;
  name: string;
}
export interface TeamPromptGroup {
  teamId: string;
  teamName: string;
  prompts: PromptSummary[];
}

export interface AgentHit {
  kind: "agent";
  id: string;
  name: string;
  role: string;
  teamId: string;
  teamName: string;
  instance: ManagedAgentInstanceSummary;
}
export interface TeamHit {
  kind: "team";
  id: string;
  name: string;
}
export interface PromptHit {
  kind: "prompt";
  id: string;
  name: string;
  description: string;
  source: "team" | "marketplace";
  /** Set for team prompts — drives the PromptViewDialog team variant. */
  teamId?: string;
  /** Author/owner team name — the dialog chip + a result sublabel. */
  teamName?: string;
}
export type SearchHit = AgentHit | TeamHit | PromptHit;

export interface SearchSources {
  agents: AgentEntry[];
  teams: TeamEntry[];
  prompts: PromptHit[];
}

export interface HomeSearchResults {
  agents: AgentHit[];
  teams: TeamHit[];
  prompts: PromptHit[];
}

/** Merge each team's own prompts with the published marketplace prompts into one
 * searchable list, de-duplicated by id (a team prompt the user can already open
 * wins over its marketplace copy, since the team variant needs no extra fetch). */
export function unifyPrompts(teamGroups: TeamPromptGroup[], marketplace: MarketplacePromptSummary[]): PromptHit[] {
  const seen = new Set<string>();
  const out: PromptHit[] = [];
  for (const group of teamGroups) {
    for (const prompt of group.prompts) {
      if (seen.has(prompt.id)) continue;
      seen.add(prompt.id);
      out.push({
        kind: "prompt",
        id: prompt.id,
        name: prompt.name,
        description: prompt.description ?? "",
        source: "team",
        teamId: group.teamId,
        teamName: group.teamName,
      });
    }
  }
  for (const prompt of marketplace) {
    if (seen.has(prompt.id)) continue;
    seen.add(prompt.id);
    out.push({
      kind: "prompt",
      id: prompt.id,
      name: prompt.name,
      description: prompt.description ?? "",
      source: "marketplace",
      teamName: prompt.team_name,
    });
  }
  return out;
}

function matches(query: string, ...fields: (string | null | undefined)[]): boolean {
  return fields.some((field) => (field ?? "").toLowerCase().includes(query));
}

/** Filter each group to the items matching `rawQuery` (case-insensitive substring
 * on name + a secondary field), capped per group. Empty query → no results (the
 * menu only opens once the user types). */
export function filterHomeSearch(
  sources: SearchSources,
  rawQuery: string,
  cap = HOME_SEARCH_GROUP_CAP,
): HomeSearchResults {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return { agents: [], teams: [], prompts: [] };

  const agents: AgentHit[] = [];
  for (const entry of sources.agents) {
    const { instance } = entry;
    if (matches(query, instance.display_name, instance.role, instance.description)) {
      agents.push({
        kind: "agent",
        id: instance.agent_instance_id,
        name: instance.display_name,
        role: instance.role,
        teamId: entry.teamId,
        teamName: entry.teamName,
        instance,
      });
      if (agents.length >= cap) break;
    }
  }

  const teams: TeamHit[] = [];
  for (const team of sources.teams) {
    if (matches(query, team.name)) {
      teams.push({ kind: "team", id: team.id, name: team.name });
      if (teams.length >= cap) break;
    }
  }

  const prompts: PromptHit[] = [];
  for (const prompt of sources.prompts) {
    if (matches(query, prompt.name, prompt.description)) {
      prompts.push(prompt);
      if (prompts.length >= cap) break;
    }
  }

  return { agents, teams, prompts };
}

/** Agents → Teams → Prompts, flattened in render order for keyboard navigation. */
export function flattenResults(results: HomeSearchResults): SearchHit[] {
  return [...results.agents, ...results.teams, ...results.prompts];
}

export function totalResultCount(results: HomeSearchResults): number {
  return results.agents.length + results.teams.length + results.prompts.length;
}
