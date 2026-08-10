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
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useSelectedTeam } from "../../../../../../hooks/useSelectedTeam.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { hasElevatedTeamRole } from "@hooks/teamCapabilities.ts";
import { IconType } from "@shared/utils/Type.ts";

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
  const location = useLocation();
  const { pathname } = location;
  const navigate = useNavigate();

  const { teamId, isPersonalTeam, selectedTeam, canOpenTeamSettings } = useSelectedTeam();

  // "Back" from a focused view (settings / usage) always returns to the team's
  // main content view — a fixed, predictable destination. `navigate(-1)` was
  // tried first but reads as arbitrary: from settings it pops one entry off
  // the raw browser history stack, which is very often another settings tab
  // (e.g. Members -> Parameters -> Back lands back on Members), not a place a
  // "Back" affordance should land on.
  const handleBack = () => {
    navigate(`/team/${teamId}/agents`);
  };
  const capabilities = useTeamCapabilities(selectedTeam);
  const { canUpdateAgents, canUpdateInfo } = capabilities;

  const settingsBase = `/team/${teamId}/settings`;
  const inSettings = !!teamId && pathname.startsWith(settingsBase);

  // The personal space has no team-admin permission to gate a settings icon on
  // (`canOpenTeamSettings` is always false there — OBSERV-02 / BACKLOG.md §7b),
  // so it reuses the same banner icon slot to open the personal usage
  // dashboard instead. The two conditions are mutually exclusive by
  // construction: a personal space is never `canOpenTeamSettings`.
  const usageBase = `/team/${teamId}/usage`;
  const inUsage = !!teamId && pathname.startsWith(usageBase);

  // #2100: which roles the current user holds on this team, "Admin · Analyst"
  // style — `permissions` alone cannot answer this (can_run_evaluations/
  // can_manage_evaluation_corpus are granted to team_analyst AND team_admin,
  // so it can't tell a plain admin from an admin who is also analyst), hence
  // the dedicated `my_relations` field. Not shown for the personal space (not
  // a team with "roles" in this sense) or for a non-member merely browsing a
  // public/marketplace team pre-join.
  //
  // `selectedTeam` can transiently be the bootstrap-cached summary (plain
  // `Team`, no `my_relations` key at all) before the dedicated per-team fetch
  // resolves — same gap `TeamSettingsPage` already guards against for
  // `permissions`. Without this check the banner renders with the incomplete
  // summary (it mounts earlier than the settings page) and shows the "no
  // elevated role" fallback for every user until the real fetch lands.
  const relationsLoaded = !!selectedTeam && "my_relations" in selectedTeam;
  // Plain "Admin · Analyste"-style text, priority-sorted (admin > editor >
  // analyst); no shield glyph — the team panel header keeps the roles line
  // typographic only, matching the Home team list item (#2298).
  const roleLabel = (() => {
    const priority: Record<string, number> = { team_admin: 0, team_editor: 1, team_analyst: 2 };
    const heldRoles = (selectedTeam?.my_relations ?? [])
      .filter((relation) => relation in priority)
      .slice()
      .sort((a, b) => priority[a] - priority[b]);
    if (heldRoles.length === 0) return t("rework.teamRoles.team_member");
    return heldRoles.map((relation) => t(`rework.teamRoles.${relation}`)).join(" · ");
  })();
  const showRoleLabel = !isPersonalTeam && !!selectedTeam?.is_member && relationsLoaded;

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
  if (canSeeActivity) {
    // Same elevated-role gate as Activity: the team usage dashboard
    // (OBSERV-02 v3) has been reachable by direct URL only — this is its
    // first in-app entry point for a real (non-personal) team.
    settingsItems.push({
      type: "link",
      label: t("rework.teamSettings.navigation.usage"),
      icon: { category: "outlined", type: "analytics", filled: false },
      linkProps: { to: usageBase },
    });
  }
  if (canSeeActivity) {
    // TEAM-05, #2118: same elevated-role gate as Activity/Usage for
    // visibility (team_admin/team_editor/team_analyst all may read) — the
    // page itself renders read-only for anyone without canUpdateResources
    // (team_editor), same read/write split TeamSettingsPage already applies.
    settingsItems.push({
      type: "link",
      label: t("rework.teamSettings.navigation.routing"),
      icon: { category: "outlined", type: "hub", filled: false },
      linkProps: { to: `${settingsBase}/routing` },
    });
  }

  const backButton = (
    <span className={styles["settings-back-container"]}>
      <Button
        color={"primary"}
        variant={"text"}
        size={"medium"}
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
          {!isPersonalTeam && <span className={styles.teamPanelKicker}>{t("rework.sidebar.team.teamLabel")}</span>}
          <span className={styles.teamPanelName}>
            {isPersonalTeam ? t("rework.sidebar.team.userTeam") : selectedTeam?.name}
          </span>
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
            {/* Usage is one of `settingsItems` (line ~186) — being on it highlights
                that entry via NavLink's own active-route match, so this doubles as
                "which tab am I on" instead of a bare, contextless Back. */}
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
            <ChatList teamId={teamId} />
          </>
        )}
      </div>
    </div>
  );
}
