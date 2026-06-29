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
import { useParams } from "react-router-dom";
import { useGetTeamQuery } from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { PERSONAL_TEAM_COLOR, teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import ChatList from "@shared/organisms/ChatList/ChatList.tsx";
import React, { useState } from "react";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import TeamSettingsPanel from "@shared/organisms/TeamSettingsPanel/TeamSettingsPanel.tsx";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap.ts";

/**
 * Team-scoped sidebar section.
 *
 * Uses `useFrontendBootstrap` for the personal-team identity and
 * `useGetTeamQuery` for collaborative-team data. The bootstrap hook is the
 * authoritative source for the active team; the RTK query fills in full
 * `TeamWithPermissions` when the route is a collaborative team.
 *
 * Mount inside the main sidebar layout for routes under `/team/:teamId/...`
 */
export default function TeamContentNavbar() {
  const { agentIconName, agentsNicknamePlural, defaultPersonalBannerFile, defaultTeamBannerFile } =
    useFrontendProperties();
  const [isTeamSettingsOpen, setIsTeamSettingsOpen] = useState(false);
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  // Identity is derived from the id shape (`personal-<uuid>`), not from a
  // comparison against the bootstrap-loaded activeTeam.id. On the very first
  // landing activeTeam is still loading, so the old comparison fell through to
  // the non-personal colour path and the banner rendered mustard instead of the
  // personal brand violet until the user switched teams and came back.
  const isPersonalTeam = isPersonalTeamId(teamId) || teamId === activeTeam?.id;

  const { data: team } = useGetTeamQuery({ teamId: teamId }, { skip: !teamId || isPersonalTeam });
  const bootstrapTeam = isPersonalTeam ? activeTeam : availableTeams.find((candidate) => candidate.id === teamId);
  const selectedTeam = isPersonalTeam ? activeTeam : (team ?? bootstrapTeam);
  const canOpenTeamSettings =
    selectedTeam && "permissions" in selectedTeam && Array.isArray(selectedTeam.permissions)
      ? selectedTeam.permissions.includes("can_administer_owners")
      : false;

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

  const bannerColor = isPersonalTeam ? PERSONAL_TEAM_COLOR : teamColor(selectedTeam?.name ?? "");
  const defaultBannerFile = isPersonalTeam ? defaultPersonalBannerFile : defaultTeamBannerFile;
  const bannerImageUrl = selectedTeam?.banner_image_url ?? (defaultBannerFile ? `/images/${defaultBannerFile}` : null);
  // Keep the brand gradient as a base layer underneath the banner image so the
  // white banner text stays legible even when the configured image is missing or
  // fails to load. Previously, supplying an image URL suppressed the gradient
  // entirely; a 404 then left the text on the bare theme surface — white-on-white
  // and unreadable in light mode. The image, when it loads, is layered on top and
  // covers the gradient, so the rendered look is unchanged in the normal case.
  const bannerStyle = {
    backgroundImage: bannerImageUrl ? `url(${bannerImageUrl}), ${bannerColor.banner}` : bannerColor.banner,
    color: bannerColor.onSolid,
  } as React.CSSProperties;

  return (
    <>
      <div className={styles.teamContentNavbarContainer}>
        <div className={styles.bannerContainer} style={bannerStyle}>
          <div className={styles.teamNameContainer}>
            <span className={styles.teamName}>
              {isPersonalTeam ? t("rework.sidebar.team.userTeam") : selectedTeam?.name}
            </span>
            {canOpenTeamSettings && (
              <span className={styles["user-settings-button-container"]}>
                <IconButton
                  size={"small"}
                  color={"on-surface"}
                  variant={"icon"}
                  icon={{ category: "outlined", type: "settings", filled: true }}
                  style={{ color: bannerColor.onSolid }}
                  onClick={() => {
                    setIsTeamSettingsOpen(true);
                  }}
                />
              </span>
            )}
          </div>
        </div>
        <div className={styles.navigationContainer}>
          <NavigationMenu items={navigationItems} />
          <Separator margin={"var(--spacing-m)"} />
          <ChatList teamId={teamId} />
        </div>
      </div>
      <FullPageModal
        isOpen={isTeamSettingsOpen && canOpenTeamSettings}
        onClose={() => setIsTeamSettingsOpen(false)}
        id="user-settings-modal"
      >
        {selectedTeam && (
          <TeamSettingsPanel modalInteraction={{ close: () => setIsTeamSettingsOpen(false) }} team={selectedTeam} />
        )}
      </FullPageModal>
    </>
  );
}
