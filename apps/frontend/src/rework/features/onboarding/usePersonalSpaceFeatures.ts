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

import { useMemo } from "react";
import { useFrontendBootstrap } from "../../../hooks/useFrontendBootstrap";
import { useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { useWikiAvailabilityQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { CAP_TEAM_WIKI } from "@components/pages/TeamAgentsPage/AgentFormModal/toolPacks";

export interface PersonalSpaceFeatures {
  /** Capability ids an agent of the personal space can use, plus `team_wiki` when its wiki is on. */
  features: ReadonlySet<string>;
  /** False until both answers are in: tours that need a feature stay hidden meanwhile. */
  loaded: boolean;
}

/**
 * What the personal space offers, so the tutorial only lists tours the user can follow
 * there. Capabilities come from its agent templates (already filtered by what the platform
 * admin grants the space); the wiki has its own switch.
 */
export function usePersonalSpaceFeatures(skip = false): PersonalSpaceFeatures {
  const { activeTeam } = useFrontendBootstrap();
  const teamId = activeTeam?.id ?? "";
  const templates = useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery(
    { teamId },
    { skip: skip || !teamId },
  );
  const wiki = useWikiAvailabilityQuery({ teamId }, { skip: skip || !teamId });

  return useMemo(() => {
    const features = new Set(
      (templates.data ?? []).flatMap((template) => (template.available_capabilities ?? []).map((cap) => cap.id)),
    );
    if (wiki.data?.enabled === true) features.add(CAP_TEAM_WIKI);
    else features.delete(CAP_TEAM_WIKI);
    // A failed answer counts as an answer: the tours needing it stay hidden, the rest show.
    const settled = (query: { isLoading: boolean; isUninitialized: boolean }) =>
      !query.isLoading && !query.isUninitialized;
    return { features, loaded: settled(templates) && settled(wiki) };
  }, [templates, wiki]);
}
