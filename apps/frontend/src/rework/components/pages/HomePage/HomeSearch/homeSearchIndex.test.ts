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

import { describe, expect, it } from "vitest";
import type {
  ManagedAgentInstanceSummary,
  PromptSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { filterHomeSearch, HOME_SEARCH_GROUP_CAP, type SearchSources, unifyPrompts } from "./homeSearchIndex";

const agent = (id: string, name: string, role = "", description = ""): ManagedAgentInstanceSummary =>
  ({ agent_instance_id: id, display_name: name, role, description, status: "enabled" }) as ManagedAgentInstanceSummary;

const teamPrompt = (id: string, name: string, description = ""): PromptSummary =>
  ({
    prompt_id: id,
    space_id: "t1",
    display_name: name,
    logical_name: id,
    tags: ["search-tag"],
    description,
  }) as PromptSummary;

describe("unifyPrompts", () => {
  it("keeps the canonical space and identity and deduplicates repeated catalog entries", () => {
    const out = unifyPrompts([
      { spaceName: "Alpha", prompts: [teamPrompt("p1", "Shared"), teamPrompt("p1", "Shared")] },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ id: "p1", spaceId: "t1", logicalName: "p1", tags: ["search-tag"] });
  });
});

describe("filterHomeSearch", () => {
  const sources: SearchSources = {
    agents: [
      { instance: agent("a1", "Contract Reviewer", "Legal"), teamId: "t1", teamName: "Alpha" },
      { instance: agent("a2", "Budget Planner", "Finance"), teamId: "t1", teamName: "Alpha" },
    ],
    teams: [
      { id: "t1", name: "Alpha" },
      { id: "t2", name: "Contracts Team", avatarImageUrl: "https://cdn/contracts.png" },
    ],
    prompts: unifyPrompts([
      { spaceName: "Alpha", prompts: [teamPrompt("p1", "Contract summary", "summarize a contract")] },
    ]),
  };

  it("returns nothing for an empty query (menu stays closed)", () => {
    const r = filterHomeSearch(sources, "   ");
    expect(r.agents).toHaveLength(0);
    expect(r.teams).toHaveLength(0);
    expect(r.prompts).toHaveLength(0);
  });

  it("matches case-insensitively across agents, teams and prompts", () => {
    const r = filterHomeSearch(sources, "contract");
    expect(r.agents.map((a) => a.id)).toEqual(["a1"]);
    expect(r.teams.map((t) => t.id)).toEqual(["t2"]);
    expect(r.prompts.map((p) => p.id)).toEqual(["p1"]);
  });

  it("carries a team's avatar url onto its hit (drives the real avatar in the menu)", () => {
    const r = filterHomeSearch(sources, "contracts team");
    expect(r.teams.map((t) => t.avatarImageUrl)).toEqual(["https://cdn/contracts.png"]);
  });

  it("matches an agent on its role, not just its name", () => {
    const r = filterHomeSearch(sources, "finance");
    expect(r.agents.map((a) => a.id)).toEqual(["a2"]);
  });

  it("caps each group at HOME_SEARCH_GROUP_CAP", () => {
    const many: SearchSources = {
      agents: Array.from({ length: HOME_SEARCH_GROUP_CAP + 3 }, (_, i) => ({
        instance: agent(`a${i}`, `Helper ${i}`),
        teamId: "t1",
        teamName: "Alpha",
      })),
      teams: [],
      prompts: [],
    };
    expect(filterHomeSearch(many, "helper").agents).toHaveLength(HOME_SEARCH_GROUP_CAP);
  });
});
