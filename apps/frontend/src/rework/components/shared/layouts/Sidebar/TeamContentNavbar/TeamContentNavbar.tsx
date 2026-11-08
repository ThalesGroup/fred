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

import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { isWeaverContentRoute } from "@core/utils/weaverContentRoute";
import { useEffect } from "react";
import {
  useMySpacesQuery,
  usePromptPublicationSpacesQuery,
  useWikiAvailabilityQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamContentNavbar.module.scss";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { teamRoleLabel } from "@shared/utils/teamRoleLabel";
import { recordTeamVisit } from "@shared/utils/teamRecency.ts";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { KeyCloakService } from "../../../../../../security/KeycloakService.ts";
import ChatList from "@shared/organisms/ChatList/ChatList.tsx";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useSelectedTeam } from "../../../../../../hooks/useSelectedTeam.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { useFrontendFeatureFlag } from "@hooks/useFrontendFeatureFlag.ts";
import { IconType } from "@shared/utils/Type.ts";
import { useTeamApplications } from "@rework/features/applications/useTeamApplications.ts";
import { BetaBadge } from "@shared/atoms/BetaBadge/BetaBadge";

/**
 * Team-scoped sidebar section — the second vertical bar.
 *
 * The coloured team banner (team identity) lives here and stays mounted across
 * both normal browsing and team settings. In settings mode the lower menu swaps
 * from the team navigation (agents/resources/prompts + chats) to the settings
 * sections; the banner never disappears, so the user always sees which team
 * they are configuring. Weaver identity and roles come from `/me/spaces`;
 * legacy summaries remain a fallback for content areas not yet ported.
 *
 * Mount inside the main sidebar layout for routes under `/team/:teamId/...`
 */
export default function TeamContentNavbar() {
  const { agentIconName, agentsNicknamePlural, defaultTeamAvatarFile } = useFrontendProperties();
  const { t } = useTranslation();
  const location = useLocation();
  const { pathname } = location;
  const agentManagement = isWeaverContentRoute(pathname);
  const navigate = useNavigate();

  const { teamId, isPersonalTeam: legacyPersonalTeam, selectedTeam } = useSelectedTeam(agentManagement);
  const memberships = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: 60 });
  const space = !memberships.isError
    ? memberships.currentData?.find((item) =>
        agentManagement && teamId === "personal" ? item.kind === "personal" : item.id === teamId,
      )
    : undefined;
  const publicationTeams = usePromptPublicationSpacesQuery(
    {},
    {
      skip: !/^\/team\/[^/]+\/prompts\/?$/.test(pathname),
      refetchOnMountOrArgChange: true,
    },
  );
  const publicationTeam = !publicationTeams.isError
    ? publicationTeams.currentData?.items.find((team) => team.id === teamId)
    : undefined;
  const isPersonalTeam = space ? space.kind === "personal" : legacyPersonalTeam;
  const manage = useSpaceAccess(space?.id, "manage");
  const content = useSpaceAccess(space?.id, "read");
  const canOpenTeamSettings = manage.allowed;
  const canReadContent = content.allowed;
  // Organization prompts use this same navigation; agent workspaces remain team/project/personal.
  const hasAgentWorkspace = space?.kind !== "organization";

  const { bootstrap } = useFrontendBootstrap(agentManagement);

  // Record every entry into a team so the Home nav-panel switcher can offer a
  // "recently viewed" sort. Client-only (localStorage), best-effort.
  useEffect(() => {
    if (teamId) recordTeamVisit(teamId);
  }, [teamId]);

  // Return content readers to agents; owner-only users return to Home rather
  // than looping through the neutral landing back to this management page.
  const handleBack = () => {
    navigate(canReadContent ? `/team/${teamId}/agents` : "/home");
  };
  const capabilities = useTeamCapabilities(selectedTeam);

  const settingsBase = `/team/${teamId}/settings`;
  const inSettings = !!teamId && pathname.startsWith(settingsBase);

  // The personal space has no team-admin permission to gate a settings icon on
  // (`canOpenTeamSettings` is always false there — OBSERV-02 / BACKLOG.md §7b),
  // so it reuses the same banner icon slot to open the personal usage
  // dashboard instead. The two conditions are mutually exclusive by
  // construction: a personal space is never `canOpenTeamSettings`.
  const usageBase = `/team/${teamId}/usage`;
  const inUsage = !!teamId && pathname.startsWith(usageBase);
  const { enabled: applicationsEnabled } = useFrontendFeatureFlag("enableApplications", agentManagement);
  const { data: teamApplications, isError: applicationsError } = useTeamApplications(
    teamId,
    agentManagement || !canReadContent || isPersonalTeam || inSettings || inUsage,
  );
  // Every entry the Control Plane returns is already registered and authorized
  // for this team; Fred no longer compiles application code, so there is no
  // second, build-time compatibility question to ask here.
  const showApplications =
    canReadContent &&
    applicationsEnabled &&
    !isPersonalTeam &&
    !applicationsError &&
    (teamApplications?.items?.length ?? 0) > 0;

  // A team has a wiki when an admin has enabled the `team_wiki` agent
  // capability for it (WIKI-03) — one decision covering the team's agents and
  // its people. Hidden while the answer is unknown rather than shown
  // optimistically: an entry that appears and then vanishes on a slow answer
  // reads worse than one that arrives a moment late, and the control-plane
  // refuses the wiki routes anyway.
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

  // Display cumulative Weaver roles consistently with Home; legacy summaries
  // remain a fallback only after their relations have actually loaded.
  const relationsLoaded = !!space || (!!selectedTeam && "my_relations" in selectedTeam);
  const roleLabel = teamRoleLabel(space?.roles ?? selectedTeam?.my_relations ?? [], t);
  const showRoleLabel = !isPersonalTeam && (!!space || !!selectedTeam?.is_member) && relationsLoaded;

  // Team avatar (28×28, 4px): the team's own image, else the deployment default,
  // else colour-tinted square initials — the same chain as the Home team list
  // and the team cards, so one team looks the same on every surface. The
  // personal space keeps that list's round user avatar (UserAvatar) — the "this
  // is you" signal — sized down to fit this compact header.
  const teamDisplayName = isPersonalTeam
    ? t("rework.sidebar.team.userTeam")
    : (space?.name ?? publicationTeam?.name ?? selectedTeam?.name ?? "");
  const teamAvatar = isPersonalTeam ? (
    <UserAvatar
      name={KeyCloakService.GetUserFullName()}
      size="x-small"
      imageUrl={bootstrap?.current_user?.avatar_image_url}
    />
  ) : selectedTeam?.avatar_image_url ? (
    <img
      className={styles.teamPanelAvatar}
      src={selectedTeam.avatar_image_url}
      alt=""
      aria-hidden="true"
      width={28}
      height={28}
      decoding="async"
    />
  ) : defaultTeamAvatarFile ? (
    <img
      className={styles.teamPanelAvatar}
      src={`/images/${defaultTeamAvatarFile}`}
      alt=""
      aria-hidden="true"
      width={28}
      height={28}
      decoding="async"
    />
  ) : (
    <TeamInitials
      className={styles.teamPanelAvatar}
      name={teamDisplayName}
      size="small"
      shape="square"
      color={teamColor(teamDisplayName)}
    />
  );

  const navigationItems: NavigationMenuItemProps[] = canReadContent
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
  navigationItems.push({
    type: "link",
    label: t("rework.weaver.title"),
    icon: { category: "outlined", type: "build", filled: false },
    linkProps: { to: "/weaver/features" },
  });
  if (showKnowledgeBases) {
    navigationItems.push({
      type: "link",
      label: t("rework.sidebar.team.menu.knowledgeBases"),
      trailingBadge: <BetaBadge label={t("rework.weaver.pending")} />,
      icon: { category: "outlined", type: "database", filled: true },
      linkProps: { to: `/team/${teamId}/knowledge-bases` },
    });
  }
  if (showWiki) {
    navigationItems.push({
      type: "link",
      label: t("rework.sidebar.team.menu.wiki"),
      trailingBadge: <BetaBadge label={t("rework.wiki.betaBadge.label")} />,
      icon: { category: "outlined", type: "book_2", filled: true },
      linkProps: { to: `/team/${teamId}/wiki` },
    });
  }
  if (showApplications) {
    navigationItems.push({
      type: "link",
      label: t("rework.sidebar.team.menu.apps"),
      icon: { category: "outlined", type: "widgets", filled: true },
      linkProps: { to: `/team/${teamId}/apps` },
    });
  }

  // Membership management is the Weaver Manage surface, independent of Read.
  const settingsItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.toolGovernance.title"),
      icon: { category: "outlined", type: "tune" },
      linkProps: { to: `${settingsBase}/offers` },
    },
    {
      type: "link",
      label: t("rework.teamSettings.navigation.members"),
      icon: { category: "outlined", type: "people", filled: true },
      linkProps: { to: `${settingsBase}/members` },
    },
  ];

  const backButton = (
    <span className={styles["settings-back-container"]}>
      <Button
        color={"primary"}
        variant={"text"}
        size={"small"}
        onClick={handleBack}
        icon={{ category: "outlined", type: "arrow_back", filled: true }}
      >
        {t("rework.back")}
      </Button>
    </span>
  );

  return (
    <div className={styles.mainNavPanel}>
      {/* Team panel header (#2298): flat surface-container-high header. For a
          real team it shows the "Equipe" kicker, the team name and the user's
          roles; for the personal space, just the "Espace personnel" name (no
          kicker/roles). Present in both normal and settings/usage mode so the
          user always sees where they are. The gear opens team settings for a
          team, or the usage dashboard for the personal space. */}
      <div className={styles.teamPanelHeader}>
        <div className={styles.teamPanelHeaderText}>
          <div className={styles.teamPanelIdentity}>
            {teamAvatar}
            <div className={styles.teamPanelTitle}>
              {!isPersonalTeam && <span className={styles.teamPanelKicker}>{t("rework.sidebar.team.spaceLabel")}</span>}
              <span className={styles.teamPanelName}>
                {isPersonalTeam ? t("rework.sidebar.team.userTeam") : (space?.name ?? selectedTeam?.name)}
              </span>
            </div>
          </div>
          {showRoleLabel && <span className={styles.teamPanelRoles}>{roleLabel}</span>}
        </div>
        {!isPersonalTeam && canOpenTeamSettings && !inSettings && (
          <span className={styles.teamPanelSettingsButton}>
            <IconButton
              size={"small"}
              variant={"icon"}
              icon={{ category: "outlined", type: "settings", filled: true }}
              onClick={() => navigate(settingsBase)}
              title={t("rework.teamSettings.navigation.settings")}
            />
          </span>
        )}
        {isPersonalTeam && !inUsage && (
          <span className={styles.teamPanelSettingsButton}>
            <IconButton
              size={"small"}
              variant={"icon"}
              icon={{ category: "outlined", type: "settings", filled: true }}
              onClick={() => navigate(usageBase)}
              title={t("rework.teamUsage.title")}
            />
          </span>
        )}
      </div>
      <div className={styles.navigationContainer}>
        {inSettings || (inUsage && !isPersonalTeam) ? (
          <>
            {backButton}
            <NavigationMenu items={settingsItems} />
          </>
        ) : inUsage ? (
          // Personal space's Usage page has no sibling tabs to switch between —
          // it's the only settings-equivalent surface a personal team has
          // (OBSERV-02 / BACKLOG.md §7b) — so Back alone is still correct here.
          backButton
        ) : (
          <>
            <NavigationMenu items={navigationItems} />
            <Separator margin={"var(--spacing-m)"} />
            {canReadContent && hasAgentWorkspace && <ChatList teamId={teamId} spaceId={space?.id} />}
          </>
        )}
      </div>
    </div>
  );
}
