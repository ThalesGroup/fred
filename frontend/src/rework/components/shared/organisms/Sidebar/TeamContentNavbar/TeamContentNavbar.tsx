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
import NavigationMenu from "@shared/organisms/NavigationMenu/NavigationMenu.tsx";
import { NavigationMenuItemProps } from "@shared/organisms/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import ChatList from "@shared/organisms/ChatList/ChatList.tsx";
import React, { useState } from "react";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import TeamSettingsPage from "@components/pages/TeamSettingsPage/TeamSettingsPage.tsx";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap.ts";

/**
 * Render one team-scoped sidebar section using the bootstrap active team as the
 * personal-team source of truth.
 *
 * Why this component exists:
 * - the shell still needs a team-aware navigation block while the frontend
 *   moves away from the temporary user-details bootstrap path
 *
 * How to use it:
 * - mount it in the sidebar for routes under `/team/:teamId/...`
 *
 * Example:
 * - `<TeamContentNavbar />`
 */
export default function TeamContentNavbar() {
  const { defaultTeamBannerFile, defaultPersonalBannerFile, agentIconName, agentsNicknamePlural } =
    useFrontendProperties();
  const [isTeamSettingsOpen, setIsTeamSettingsOpen] = useState(false);
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const personalTeamId = activeTeam?.id ?? "personal";
  const isPersonalTeam = teamId === personalTeamId;

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
      label: agentsNicknamePlural.toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase()),
      icon: { category: "outlined", type: agentIconName as IconType, filled: true },
      linkProps: { to: `/team/${teamId}/agents` },
    },
    {
      type: "link",
      label: t("rework.sidebar.team.menu.resources"),
      icon: { category: "outlined", type: "folder", filled: true },
      linkProps: { to: `/team/${teamId}/resources` },
    },
  ];

  const bannerStyle = {
    "--banner-img": isPersonalTeam
      ? `url("/images/${defaultPersonalBannerFile}")`
      : `url("${selectedTeam?.banner_image_url ?? `/images/${defaultTeamBannerFile}`}")`,
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
        id={"user-settings-modal"}
      >
        {selectedTeam && (
          <TeamSettingsPage modalInteraction={{ close: () => setIsTeamSettingsOpen(false) }} team={selectedTeam} />
        )}
      </FullPageModal>
    </>
  );
}
