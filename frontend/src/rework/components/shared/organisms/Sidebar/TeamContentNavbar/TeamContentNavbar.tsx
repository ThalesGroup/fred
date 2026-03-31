import styles from "./TeamContentNavbar.module.scss";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { useGetTeamQuery } from "../../../../../../slices/controlPlane/controlPlaneApi";
import ConversationButton from "@shared/atoms/ConversationButton/ConversationButton.tsx";
import NavigationMenu from "@shared/organisms/NavigationMenu/NavigationMenu.tsx";
import { NavigationMenuItemProps } from "@shared/organisms/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import ChatList from "@shared/organisms/ChatList/ChatList.tsx";
import React, { useState } from "react";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import TeamSettingsPage from "@components/pages/TeamSettingsPage/TeamSettingsPage.tsx";

export default function TeamContentNavbar() {
  const [isTeamSettingsOpen, setIsTeamSettingsOpen] = useState(false);
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { teamId } = useParams<{ teamId: string }>();

  const { data: team } = useGetTeamQuery({ teamId: teamId !== "user" ? teamId : "" }, { skip: !teamId });
  const selectedTeam = teamId ? team : undefined;
  const canOpenTeamSettings = selectedTeam?.permissions?.includes("can_administer_owners") || false;

  const navigationItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.sidebar.team.menu.agents"),
      icon: { category: "outlined", type: "Person" },
      linkProps: { to: `/team/${teamId}/agents` },
    },
    {
      type: "link",
      label: t("rework.sidebar.team.menu.resources"),
      icon: { category: "outlined", type: "Folder" },
      linkProps: { to: `/team/${teamId}/resources` },
    },
  ];

  const newChatHandler = () => {
    navigate(`/new-chat`);
  };

  const bannerStyle = {
    "--banner-img": selectedTeam?.banner_image_url
      ? `url(${selectedTeam.banner_image_url})`
      : 'url("/images/default-team-banner.png")',
  } as React.CSSProperties;

  return (
    <>
      <div className={styles["team-content-navbar-container"]}>
        <div className={styles["banner-container"]} style={bannerStyle}>
          <div className={styles["team-name-container"]}>
            <span className={styles["team-name"]}>
              {teamId == "user" ? t("rework.sidebar.team.userTeam") : selectedTeam?.name}
            </span>
            {canOpenTeamSettings && (
              <span className={styles["user-settings-button-container"]}>
                <IconButton
                  size={"small"}
                  color={"on-surface"}
                  variant={"icon"}
                  icon={{ category: "outlined", type: "Settings", filled: true }}
                  onClick={() => {
                    setIsTeamSettingsOpen(true);
                  }}
                />
              </span>
            )}
          </div>
          <span className={styles["conversation-button-container"]}>
            <ConversationButton icon={{ category: "outlined", type: "Add" }} onClick={newChatHandler}>
              {t("rework.sidebar.newChat")}
            </ConversationButton>
          </span>
        </div>
        <div className={styles["navigation-container"]}>
          <NavigationMenu items={navigationItems} />
          <Separator margin={"var(--spacing-m)"} />
          <ChatList />
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
