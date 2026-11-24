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

import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import { canReadSpaceUsage } from "@core/utils/spaceUsage";
import { teamProjects } from "@core/utils/teamProjects";
import { sessionQueryArgs } from "../../../../../../slices/controlPlane/controlPlaneApi";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { isWeaverContentRoute } from "@core/utils/weaverContentRoute";
import { useEffect, useRef } from "react";
import {
  useMySpacesQuery,
  useGetMyAvatarQuery,
  useGetTeamAvatarQuery,
  useMarketplaceProposalSpacesQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamContentNavbar.module.scss";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { recordTeamVisit } from "@shared/utils/teamRecency.ts";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { spaceRolesCaption } from "@shared/utils/teamRoleLabel";
import SpaceUpLink from "../SpaceUpLink/SpaceUpLink.tsx";
import { useSpaceContentItems } from "../useSpaceContentItems.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import SpaceHeader from "@shared/molecules/SpaceHeader/SpaceHeader.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { KeyCloakService } from "../../../../../../security/KeycloakService.ts";
import ChatList from "@shared/organisms/ChatList/ChatList.tsx";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useSelectedTeam } from "../../../../../../hooks/useSelectedTeam.ts";

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
  const { defaultTeamAvatarFile } = useFrontendProperties();
  const { t } = useTranslation();
  const location = useLocation();
  const { pathname } = location;
  const workingOrganization = useWorkingOrganization();
  const organizationId =
    workingOrganization.loading || workingOrganization.error ? undefined : workingOrganization.organizationId;
  const agentManagement = isWeaverContentRoute(pathname);
  const navigate = useNavigate();

  const { teamId, isPersonalTeam: legacyPersonalTeam, selectedTeam } = useSelectedTeam(agentManagement);
  const memberships = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: 60 });
  const space = !memberships.isError
    ? memberships.currentData?.find((item) =>
        agentManagement && teamId === "personal"
          ? item.kind === "personal" && item.organization_id === organizationId
          : item.id === teamId,
      )
    : undefined;
  const organization = space && memberships.currentData?.find((item) => item.id === space.organization_id);
  const parentTeam =
    space?.kind === "project"
      ? memberships.currentData?.find(
          (item) =>
            item.id === space.parent_id && item.kind === "team" && item.organization_id === space.organization_id,
        )
      : undefined;
  const hasProjects = teamProjects(memberships.currentData, space).length > 0;
  const ancestors = [organization, parentTeam].filter((item) => item !== undefined && item.id !== space?.id);
  const publicationTeams = useMarketplaceProposalSpacesQuery(sessionQueryArgs({}), {
    skip: !/^\/team\/[^/]+\/prompts\/?$/.test(pathname),
    refetchOnMountOrArgChange: true,
  });
  const publicationTeam = !publicationTeams.isError
    ? publicationTeams.currentData?.items.find((team) => team.id === teamId)
    : undefined;
  const isPersonalTeam = space ? space.kind === "personal" : legacyPersonalTeam;
  const manage = useSpaceAccess(space?.id, "manage");
  const content = useSpaceAccess(space?.id, "read");
  // Navigation uses the last successful answer while access is rechecked.
  // This does not authorize page actions; access errors offer a retry below.
  const canOpenTeamSettings =
    manage.offered || ((space?.kind === "team" || space?.kind === "project") && content.offered);
  const canReadConsumption = canReadSpaceUsage(space, organizationId);
  const canReadContent = content.offered;
  // Organizations have no agent workspace, hence no conversations.
  const hasAgentWorkspace = space?.kind !== "organization";

  const { currentData: pictureUrl } = useGetMyAvatarQuery(undefined, {
    skip: !isPersonalTeam,
    refetchOnMountOrArgChange: 60,
  });

  const teamPicture = useGetTeamAvatarQuery(
    { id: space?.id ?? "" },
    {
      skip: space?.kind !== "team" || (!manage.allowed && !content.allowed),
      refetchOnMountOrArgChange: 60,
    },
  );
  const teamPictureUrl = !teamPicture.isError ? teamPicture.currentData : undefined;

  // Record every entry into a team so the organization nav panel can offer a
  // "recently viewed" sort. Client-only (localStorage), best-effort.
  useEffect(() => {
    if (teamId) recordTeamVisit(teamId);
  }, [teamId]);

  // Content readers return through their space landing. An organization's panel lives at /home, and
  // owner-only users go there rather than loop through the landing back to this management page.
  const handleBack = () => {
    if (space?.kind === "organization") navigate("/home", { state: { focusSettings: true } });
    else navigate(canReadContent ? `/team/${teamId}` : "/home");
  };

  const settingsBase = `/team/${teamId}/settings`;
  const inSettings = !!teamId && pathname.startsWith(settingsBase);

  // Consumption stays in settings navigation; personal usage keeps its header shortcut.
  const usageBase = `/team/${teamId}/usage`;
  const inUsage = !!teamId && pathname.startsWith(usageBase);
  // Opened from a gear: focus moves into the settings panel, starting on its back button.
  const backContainer = useRef<HTMLSpanElement>(null);
  const focusPanel = (location.state as { focusPanel?: boolean } | null)?.focusPanel === true;
  useEffect(() => {
    if (focusPanel && (inSettings || inUsage)) backContainer.current?.querySelector<HTMLElement>("button")?.focus();
  }, [focusPanel, inSettings, inUsage]);

  const rolesCaption = isPersonalTeam ? undefined : spaceRolesCaption(space?.roles ?? [], t);

  // Team avatar (28×28, 4px): the team's own image, else the deployment default,
  // else colour-tinted square initials — the same chain as the organization team list
  // and the team cards, so one team looks the same on every surface. The
  // personal space keeps that list's round user avatar (UserAvatar) — the "this
  // is you" signal — sized down to fit this compact header.
  const teamDisplayName = isPersonalTeam
    ? t("rework.sidebar.team.userTeam")
    : (space?.name ?? publicationTeam?.name ?? selectedTeam?.name ?? "");
  const teamAvatar = isPersonalTeam ? (
    <UserAvatar name={KeyCloakService.GetUserFullName()} size="x-small" imageUrl={pictureUrl || undefined} />
  ) : (space ? teamPictureUrl : selectedTeam?.avatar_image_url) ? (
    <img
      className={styles.teamPanelAvatar}
      src={(space ? teamPictureUrl : selectedTeam?.avatar_image_url) ?? undefined}
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

  const navigationItems = useSpaceContentItems({
    teamId,
    space,
    canReadContent,
    isPersonalTeam,
    selectedTeam,
    skipApplications: inSettings || inUsage,
    showProjects: space?.kind === "team" && (canReadContent || hasProjects),
  });

  const activityItems: NavigationMenuItemProps[] =
    canReadContent && space?.kind === "team"
      ? [
          {
            type: "link",
            label: t("rework.teamSettings.navigation.activity"),
            icon: { category: "outlined", type: "history" },
            linkProps: { to: `${settingsBase}/activity` },
          },
        ]
      : [];

  const usageItems: NavigationMenuItemProps[] = canReadConsumption
    ? [
        {
          type: "link",
          label: t("rework.teamSettings.navigation.usage"),
          icon: { category: "outlined", type: "analytics", filled: false },
          linkProps: { to: usageBase },
        },
      ]
    : [];

  const personalUsageItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.teamUsage.title"),
      icon: { category: "outlined", type: "analytics", filled: false },
      linkProps: { to: usageBase },
    },
  ];

  // Membership management is the Weaver Manage surface, independent of Read.
  const settingsItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.spaceModels.title"),
      icon: { category: "outlined", type: "tune" },
      linkProps: { to: `${settingsBase}/models` },
    },
    ...(manage.offered
      ? ([
          {
            type: "link",
            label: t("rework.toolGovernance.title"),
            icon: { category: "outlined", type: "tune" },
            linkProps: { to: `${settingsBase}/offers` },
          },
        ] satisfies NavigationMenuItemProps[])
      : []),
    {
      type: "link",
      label: t("rework.teamSettings.navigation.members"),
      icon: { category: "outlined", type: "people", filled: true },
      linkProps: { to: `${settingsBase}/members` },
    },
  ];

  if (space?.kind === "team" && manage.offered) {
    settingsItems.unshift({
      type: "link",
      label: t("rework.teamSettings.navigation.parameters"),
      icon: { category: "outlined", type: "settings" },
      linkProps: { to: `${settingsBase}/parameters` },
    });
  }

  // The quiet link up to the parent space always tops the panel; leaving settings sits under the header.
  const parent = ancestors[ancestors.length - 1];
  const up =
    space && parent
      ? {
          name: parent.name,
          kind: parent.kind,
          onClick: () => navigate(parent.kind === "organization" ? "/home" : `/team/${parent.id}`),
        }
      : undefined;
  const leaveSettings = inSettings || inUsage;

  return (
    <div className={styles.mainNavPanel}>
      {up && (
        <SpaceUpLink name={up.name} kind={up.kind === "organization" ? "organization" : "team"} onClick={up.onClick} />
      )}
      {/* Every space shares one header, settings included; an organization is only reached here for its settings. */}
      {space?.kind === "organization" ? (
        <SpaceHeader
          leading={<Icon category="outlined" type="domain" />}
          eyebrow={t("rework.manager.kinds.organization")}
          title={space.name}
          caption={rolesCaption}
        />
      ) : (
        <SpaceHeader
          leading={teamAvatar}
          eyebrow={
            isPersonalTeam
              ? undefined
              : t(space ? `rework.userSettings.spaceKinds.${space.kind}` : "rework.sidebar.team.spaceLabel")
          }
          title={teamDisplayName}
          caption={rolesCaption}
          action={
            !isPersonalTeam &&
            (canOpenTeamSettings || canReadConsumption || activityItems.length > 0) &&
            !inSettings &&
            !inUsage ? (
              <IconButton
                size="small"
                variant="icon"
                icon={{ category: "outlined", type: "settings", filled: true }}
                onClick={() =>
                  navigate(
                    canOpenTeamSettings
                      ? `${settingsBase}/members`
                      : canReadConsumption
                        ? usageBase
                        : `${settingsBase}/activity`,
                    { state: { focusPanel: true } },
                  )
                }
                title={t("rework.teamSettings.navigation.settings")}
              />
            ) : isPersonalTeam && !inUsage ? (
              <IconButton
                size="small"
                variant="icon"
                icon={{ category: "outlined", type: "settings", filled: true }}
                onClick={() => navigate(usageBase)}
                title={t("rework.teamUsage.title")}
              />
            ) : undefined
          }
        />
      )}
      {leaveSettings && (
        <span ref={backContainer} className={`${styles["settings-back-container"]} ${styles.closeSettings}`}>
          <Button
            color={"primary"}
            variant={"text"}
            size={"small"}
            onClick={handleBack}
            icon={{ category: "outlined", type: "close", filled: true }}
          >
            {t("rework.teamSettings.navigation.closeSettings")}
          </Button>
        </span>
      )}
      <div className={styles.navigationContainer}>
        {(content.error || manage.error) && (
          <ServiceNotice
            color="error"
            title={t("rework.sidebar.team.accessError")}
            action={
              <IconButton
                size="small"
                variant="icon"
                icon={{ category: "outlined", type: "refresh" }}
                aria-label={t("common.retry")}
                title={t("common.retry")}
                onClick={() => {
                  if (content.error) void content.refetch();
                  if (manage.error) void manage.refetch();
                }}
              />
            }
          />
        )}
        {inSettings || (inUsage && !isPersonalTeam) ? (
          <NavigationMenu items={[...(canOpenTeamSettings ? settingsItems : []), ...activityItems, ...usageItems]} />
        ) : inUsage ? (
          // Personal usage has no membership-management tabs, only its own entry.
          <NavigationMenu items={personalUsageItems} />
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
