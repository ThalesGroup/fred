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
import { useGetUserDetailsControlPlaneV1UserGetQuery } from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";

export default function TeamContentNavbar() {
  const { defaultTeamBannerFile, agentIconName, agentsNicknamePlural } = useFrontendProperties();
  const [isTeamSettingsOpen, setIsTeamSettingsOpen] = useState(false);
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  const { data: userDetails } = useGetUserDetailsControlPlaneV1UserGetQuery();

  const { data: team } = useGetTeamQuery(
    { teamId: teamId },
    { skip: !teamId || teamId === userDetails?.personalTeam.id },
  );
  const selectedTeam = teamId === userDetails?.personalTeam.id ? userDetails?.personalTeam : team;
  const canOpenTeamSettings = selectedTeam?.permissions?.includes("can_administer_owners") || false;

  const navigationItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: agentsNicknamePlural.toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase()),
      icon: { category: "outlined", type: agentIconName as IconType },
      linkProps: { to: `/team/${teamId}/agents` },
    },
    {
      type: "link",
      label: t("rework.sidebar.team.menu.resources"),
      icon: { category: "outlined", type: "folder" },
      linkProps: { to: `/team/${teamId}/resources` },
    },
  ];

  const bannerStyle = {
    "--banner-img": selectedTeam?.banner_image_url
      ? `url(${selectedTeam.banner_image_url})`
      : `url("/images/${defaultTeamBannerFile}")`,
  } as React.CSSProperties;

  return (
    <>
      <div className={styles.teamContentNavbarContainer}>
        <div className={styles.bannerContainer} style={bannerStyle}>
          <div className={styles.teamNameContainer}>
            <span className={styles.teamName}>
              {teamId == userDetails?.personalTeam.id ? t("rework.sidebar.team.userTeam") : selectedTeam?.name}
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
