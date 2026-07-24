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

import styles from "./TeamContentNavbar.module.scss";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import ChatList from "@shared/organisms/ChatList/ChatList.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider.tsx";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useSelectedTeam } from "../../../../../../hooks/useSelectedTeam.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { hasElevatedTeamRole } from "@hooks/teamCapabilities.ts";
import { IconType } from "@shared/utils/Type.ts";
import { KeyCloakService } from "../../../../../../security/KeycloakService";
import {
  useListTeamMembersQuery,
  useRemoveTeamMemberMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";

/**
 * Team-scoped sidebar section — the second vertical bar.
 *
 * The coloured team banner (team identity) lives here and stays mounted across
 * both normal browsing and team settings. In settings mode the lower menu swaps
 * from the team navigation (agents/resources/prompts + chats) to the settings
 * sections; the banner never disappears, so the user always sees which team
 * they are configuring. Team/banner state comes from `useSelectedTeam`, shared
 * with the routed `TeamSettingsPage`.
 *
 * Mount inside the main sidebar layout for routes under `/team/:teamId/...`
 */
export default function TeamContentNavbar() {
  const { agentIconName, agentsNicknamePlural } = useFrontendProperties();
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { teamId, isPersonalTeam, selectedTeam, canOpenTeamSettings, bannerColor, bannerStyle } = useSelectedTeam();
  const capabilities = useTeamCapabilities(selectedTeam);
  const { canUpdateAgents, canUpdateInfo, canAdministerAdmins } = capabilities;
  const { showConfirmationDialog } = useConfirmationDialog();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const [removeTeamMember] = useRemoveTeamMemberMutation();

  const settingsBase = `/team/${teamId}/settings`;
  const inSettings = !!teamId && pathname.startsWith(settingsBase);

  // Only an admin can ever be blocked from leaving (the "at least one
  // team_admin" invariant, AUTHZ-09) — skip the lookup for everyone else.
  const { data: teamMembers } = useListTeamMembersQuery(
    { teamId: teamId ?? "" },
    { skip: !inSettings || !teamId || !canAdministerAdmins },
  );
  const adminCount = teamMembers?.filter((member) => member.relations.includes("team_admin")).length ?? 0;
  const isLastAdmin = canAdministerAdmins && adminCount <= 1;

  // The personal space has no team-admin permission to gate a settings icon on
  // (`canOpenTeamSettings` is always false there — OBSERV-02 / BACKLOG.md §7b),
  // so it reuses the same banner icon slot to open the personal usage
  // dashboard instead. The two conditions are mutually exclusive by
  // construction: a personal space is never `canOpenTeamSettings`.
  const usageBase = `/team/${teamId}/usage`;
  const inUsage = !!teamId && pathname.startsWith(usageBase);

  const navigationItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: (agentsNicknamePlural ?? "").toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase()),
      icon: { category: "outlined", type: agentIconName as IconType, filled: true },
      linkProps: { to: `/team/${teamId}/agents` },
    },
    {
      type: "link",
      label: t("rework.sidebar.team.menu.resources"),
      icon: { category: "outlined", type: "folder", filled: true },
      linkProps: { to: `/team/${teamId}/resources` },
    },
    {
      type: "link",
      label: "Prompts",
      icon: { category: "outlined", type: "edit_note", filled: true },
      linkProps: { to: `/team/${teamId}/prompts` },
    },
  ];

  // Launching and cancelling evaluation campaigns requires agent-update rights
  // (AGENT-EVALUATION-RFC §8.4), not member administration — so the Evaluations
  // section is gated separately from the settings entry point itself.
  const canManageEvaluations = canUpdateAgents;

  // AUTHZ-09: the settings entry point is now open to every team member
  // (`canOpenTeamSettings` = `canReadMembers`), so Activity — meant only for
  // elevated roles, not the baseline member surface — needs its own gate
  // instead of reusing the membership-level check the backend's GET /tasks
  // happens to accept.
  const canSeeActivity = hasElevatedTeamRole(capabilities);

  const settingsItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.teamSettings.navigation.members"),
      icon: { category: "outlined", type: "people", filled: true },
      linkProps: { to: `${settingsBase}/members` },
    },
  ];
  if (canUpdateInfo) {
    settingsItems.push({
      type: "link",
      label: t("rework.teamSettings.navigation.settings"),
      icon: { category: "outlined", type: "settings", filled: true },
      linkProps: { to: `${settingsBase}/parameters` },
    });
  }
  if (canSeeActivity) {
    // Same "build" icon as the platform admin Tasks entry — one shared surface,
    // identical ergonomy at both levels (OPS-04 §3.4).
    settingsItems.push({
      type: "link",
      label: t("rework.teamSettings.navigation.activity"),
      icon: { category: "outlined", type: "build", filled: false },
      linkProps: { to: `${settingsBase}/activity` },
    });
  }
  if (canManageEvaluations) {
    settingsItems.push({
      type: "link",
      label: t("rework.teamSettings.navigation.evaluations"),
      icon: { category: "outlined", type: "reviews", filled: false },
      linkProps: { to: `${settingsBase}/evaluations` },
    });
  }

  const handleLeaveTeam = () => {
    if (!teamId || isLastAdmin) return;
    showConfirmationDialog({
      title: t("rework.teamSettings.leaveTeam.title"),
      message: t("rework.teamSettings.leaveTeam.message", { teamName: selectedTeam?.name ?? "" }),
      confirmButtonLabel: t("rework.teamSettings.leaveTeam.confirmLabel"),
      criticalAction: true,
      cancelVariant: "filled",
      cancelColor: "primary",
      confirmVariant: "text",
      onConfirm: async () => {
        const userId = KeyCloakService.GetUserId();
        if (!userId) return;
        await runMutationAction({
          action: () => removeTeamMember({ teamId, userId }).unwrap(),
          onError: (error) =>
            notifyApiError(error, {
              summary: t("rework.teamSettings.leaveTeam.errors.summary"),
              fallbackDetail: t("rework.teamSettings.leaveTeam.errors.fallbackDetail"),
              forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail"),
              conflictDetail: t("rework.teamSettings.members.errors.lastOwnerDetail"),
            }),
          onSuccess: () => navigate("/team/personal/agents"),
        });
      },
    });
  };

  return (
    <div className={styles.teamContentNavbarContainer}>
      <div className={styles.bannerContainer} style={bannerStyle}>
        <div className={styles.teamNameContainer}>
          <span className={styles.teamName}>
            {isPersonalTeam ? t("rework.sidebar.team.userTeam") : selectedTeam?.name}
          </span>
          {canOpenTeamSettings && !inSettings && (
            <span className={styles["user-settings-button-container"]}>
              <IconButton
                size={"small"}
                color={"on-surface"}
                variant={"icon"}
                icon={{ category: "outlined", type: "settings", filled: true }}
                style={{ color: bannerColor?.onSolid }}
                onClick={() => navigate(settingsBase)}
                title={t("rework.teamSettings.navigation.settings")}
              />
            </span>
          )}
          {isPersonalTeam && !inUsage && (
            <span className={styles["user-settings-button-container"]}>
              <IconButton
                size={"small"}
                color={"on-surface"}
                variant={"icon"}
                icon={{ category: "outlined", type: "settings", filled: true }}
                style={{ color: bannerColor?.onSolid }}
                onClick={() => navigate(usageBase)}
                title={t("rework.teamUsage.title")}
              />
            </span>
          )}
        </div>
      </div>
      <div className={styles.navigationContainer}>
        {inSettings ? (
          <>
            <span className={styles["settings-back-container"]}>
              <Button
                color={"primary"}
                variant={"text"}
                size={"medium"}
                onClick={() => navigate(`/team/${teamId}/agents`)}
                icon={{ category: "outlined", type: "arrow_back", filled: true }}
              >
                {t("rework.back")}
              </Button>
            </span>
            <NavigationMenu items={settingsItems} />
            <span className={styles["leave-team-container"]}>
              <Button
                color={"error"}
                variant={"filled"}
                size={"medium"}
                disabled={isLastAdmin}
                title={isLastAdmin ? t("rework.teamSettings.leaveTeam.lastAdminTooltip") : undefined}
                onClick={handleLeaveTeam}
                className={styles["leave-team-button"]}
              >
                {t("rework.teamSettings.navigation.leaveTeam")}
              </Button>
            </span>
          </>
        ) : inUsage ? (
          // Same focused-view treatment as settings: the usage dashboard
          // replaces team browsing, so the agents/resources/prompts nav and
          // chat list step aside for a single Back action (OBSERV-02 /
          // BACKLOG.md §7b — keeps the experience consistent for everyone,
          // whether reached from the admin/observer rail or here).
          <span className={styles["settings-back-container"]}>
            <Button
              color={"primary"}
              variant={"text"}
              size={"medium"}
              onClick={() => navigate(`/team/${teamId}/agents`)}
              icon={{ category: "outlined", type: "arrow_back", filled: true }}
            >
              {t("rework.back")}
            </Button>
          </span>
        ) : (
          <>
            <NavigationMenu items={navigationItems} />
            <Separator margin={"var(--spacing-m)"} />
            <ChatList teamId={teamId} />
          </>
        )}
      </div>
    </div>
  );
}
