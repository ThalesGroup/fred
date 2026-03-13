import styles from "./TeamContentNavbar.module.scss";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useGetTeamQuery } from "../../../../../../slices/controlPlane/controlPlaneApi";
import ConversationButton from "@shared/atoms/ConversationButton/ConversationButton.tsx";
import NavigationMenu from "@shared/organisms/NavigationMenu/NavigationMenu.tsx";
import { NavigationMenuItemProps } from "@shared/organisms/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import ChatList from "@shared/organisms/ChatList/ChatList.tsx";
import React from "react";

export default function TeamContentNavbar() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { teamId } = useParams<{ teamId: string }>();

  const { data: team, isLoading } = useGetTeamQuery(
    { teamId: teamId || "" },
    { skip: !teamId },
  );

  const teamsNavigationItems: NavigationMenuItemProps[] = [
    {
      label: t("rework.sidebar.menu.agents"),
      icon: { category: "outlined", type: "Person" },
      selected: false,
      link: `/team/${teamId}/agents`,
    },
    {
      label: t("rework.sidebar.menu.resources"),
      icon: { category: "outlined", type: "Folder" },
      selected: false,
      link: `/team/${teamId}/resources`,
    },
    {
      label: t("rework.sidebar.menu.apps"),
      icon: { category: "outlined", type: "Widgets" },
      selected: false,
      link: `/team/${teamId}/apps`,
    },
  ];

  const userNavigationItems: NavigationMenuItemProps[] = [
    {
      label: t("rework.sidebar.menu.agents"),
      icon: { category: "outlined", type: "Person" },
      selected: false,
      link: `/agents`,
    },
    {
      label: t("rework.sidebar.menu.resources"),
      icon: { category: "outlined", type: "Folder" },
      selected: false,
      link: `/knowledge`,
    },
  ];

  const newChatHandler = () => {
    navigate(`/new-chat`);
  };

  const isUserSpace = !pathname.startsWith(`/team`);

  const getTeam = () => {
    if (teamId) {
      return team;
    } else {
      return undefined;
    }
  };
  const bannerStyle = {
    "--banner-img": getTeam()?.banner_image_url
      ? `url(${getTeam().banner_image_url})`
      : 'url("/images/default-team-banner.png")',
  } as React.CSSProperties;

  return (
    <div className={styles["team-content-navbar-container"]}>
      <div className={styles["banner-container"]} style={bannerStyle}>
        <div className={styles["team-name-container"]}>
          <span className={styles["team-name"]}>
            {isLoading ? "loading" : getTeam()?.name || t("rework.sidebar.team.userTeam")}
          </span>
          <span className={styles["user-settings-button-container"]}>
            <IconButton
              size={"small"}
              color={"primary"}
              variant={"icon"}
              icon={{ category: "outlined", type: "Settings", filled: true }}
            />
          </span>
        </div>
        <span className={styles["conversation-button-container"]}>
          <ConversationButton icon={{ category: "outlined", type: "Add" }} onClick={newChatHandler}>
            {t("rework.sidebar.newChat")}
          </ConversationButton>
        </span>
      </div>
      <div className={styles["navigation-container"]}>
        <NavigationMenu items={isUserSpace ? userNavigationItems : teamsNavigationItems} />
        <Separator margin={"16px"} />
        <ChatList />
      </div>
    </div>
  );
}
