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

import { useTranslation } from "react-i18next";
import { useWikiAvailabilityQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { MySpace } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { TeamWithPermissions } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import { BetaBadge } from "@shared/atoms/BetaBadge/BetaBadge";
import { IconType } from "@shared/utils/Type.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { useTeamApplications } from "@rework/features/applications/useTeamApplications.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";

/** A space's content menu, shared by the organization panel and the team/project/personal panel. */
export function useSpaceContentItems({
  teamId,
  space,
  canReadContent,
  isPersonalTeam,
  selectedTeam,
  skipApplications = false,
  showProjects = false,
}: {
  /** The route id of the space (`/team/<teamId>/...`). */
  teamId: string | undefined;
  space: MySpace | undefined;
  canReadContent: boolean;
  isPersonalTeam: boolean;
  /** Legacy summary, the fallback while a content area is not ported. */
  selectedTeam?: TeamWithPermissions | null;
  skipApplications?: boolean;
  /** A team's entry into its projects page: its first entry and landing page. */
  showProjects?: boolean;
}): NavigationMenuItemProps[] {
  const { t } = useTranslation();
  const { agentIconName, agentsNicknamePlural } = useFrontendProperties();
  const capabilities = useTeamCapabilities(selectedTeam);
  // Organization prompts use this same navigation; agent workspaces remain team/project/personal.
  const hasAgentWorkspace = space?.kind !== "organization";

  const { data: teamApplications, isError: applicationsError } = useTeamApplications(
    teamId,
    isPersonalTeam || !space || skipApplications,
  );
  // The Control Plane only returns applications already registered and authorized for this team.
  const showApplications = !isPersonalTeam && !applicationsError && (teamApplications?.length ?? 0) > 0;

  // Hidden while unknown rather than shown optimistically: an entry that vanishes reads worse than a late one.
  const { currentData: wikiAvailability, isError: wikiUnavailable } = useWikiAvailabilityQuery(
    { spaceId: space?.id ?? "" },
    {
      skip: !canReadContent || !space || !["team", "personal"].includes(space.kind),
      refetchOnMountOrArgChange: true,
    },
  );
  const showWiki = !wikiUnavailable && canReadContent && wikiAvailability?.enabled === true;
  // Porting entry only: it does not depend on the removed Swift catalog.
  const showKnowledgeBases = canReadContent && (!!space || capabilities.canUseTeamKnowledgeBases);

  const items: NavigationMenuItemProps[] = canReadContent
    ? [
        ...(hasAgentWorkspace
          ? ([
              {
                type: "link",
                label: (agentsNicknamePlural ?? "").toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase()),
                icon: { category: "outlined", type: agentIconName as IconType, filled: true },
                linkProps: { to: `/team/${teamId}/agents` },
              },
            ] satisfies NavigationMenuItemProps[])
          : []),
        {
          type: "link",
          label: t("rework.sidebar.team.menu.resources"),
          icon: { category: "outlined", type: "folder", filled: true },
          linkProps: { to: `/team/${teamId}/resources` },
        },
        {
          type: "link",
          label: t("rework.spaceSkills.title"),
          icon: { category: "outlined", type: "school", filled: true },
          linkProps: { to: `/team/${teamId}/skills` },
        },
        {
          type: "link",
          label: "Prompts",
          icon: { category: "outlined", type: "chat", filled: true },
          linkProps: { to: `/team/${teamId}/prompts` },
        },
      ]
    : [];
  if (showProjects) {
    items.unshift({
      type: "link",
      label: t("rework.sidebar.team.menu.projects"),
      icon: { category: "outlined", type: "assignment", filled: true },
      linkProps: { to: `/team/${teamId}/projects` },
    });
  }
  if (showKnowledgeBases) {
    items.push({
      type: "link",
      label: t("rework.sidebar.team.menu.knowledgeBases"),
      icon: { category: "outlined", type: "database", filled: true },
      linkProps: { to: `/team/${teamId}/knowledge-bases` },
    });
  }
  if (showWiki) {
    items.push({
      type: "link",
      label: t("rework.sidebar.team.menu.wiki"),
      trailingBadge: <BetaBadge label={t("rework.wiki.betaBadge.label")} />,
      icon: { category: "outlined", type: "book_2", filled: true },
      linkProps: { to: `/team/${teamId}/wiki` },
    });
  }
  if (showApplications) {
    items.push({
      type: "link",
      label: t("rework.sidebar.team.menu.apps"),
      icon: { category: "outlined", type: "widgets", filled: true },
      linkProps: { to: `/team/${teamId}/apps` },
    });
  }
  return items;
}
