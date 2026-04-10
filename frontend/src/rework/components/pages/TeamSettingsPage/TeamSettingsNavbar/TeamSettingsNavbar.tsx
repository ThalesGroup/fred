import styles from "./TeamSettingsNavbar.module.scss";
import { NavigationMenuItemProps } from "@shared/organisms/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import NavigationMenu from "@shared/organisms/NavigationMenu/NavigationMenu.tsx";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import Button from "@shared/atoms/Button/Button.tsx";
import { TeamSettingsMenuPanels } from "@components/pages/TeamSettingsPage/TeamSettingsPage.tsx";

interface TeamSettingsNavbarProps {
  team: TeamWithPermissions;
  close: () => void;
  changePanel: (panel: TeamSettingsMenuPanels) => void;
  panelSelected: TeamSettingsMenuPanels;
}

export default function TeamSettingsNavbar({ team, close, changePanel, panelSelected }: TeamSettingsNavbarProps) {
  const { t } = useTranslation("");

  const navigationMenu: NavigationMenuItemProps[] = [
    {
      type: "button",
      label: t("rework.teamSettings.navigation.members"),
      icon: {
        category: "outlined",
        type: "people",
        filled: true,
      },
      selected: panelSelected === TeamSettingsMenuPanels.MEMBERS,
      onClick: () => {
        changePanel(TeamSettingsMenuPanels.MEMBERS);
      },
    },
    {
      type: "button",
      label: t("rework.teamSettings.navigation.settings"),
      icon: {
        category: "outlined",
        type: "settings",
        filled: true,
      },
      selected: panelSelected === TeamSettingsMenuPanels.PARAMETERS,
      onClick: () => {
        changePanel(TeamSettingsMenuPanels.PARAMETERS);
      },
    },
  ];

  return (
    <div className={styles["team-settings-navbar"]}>
      <span className={styles["team-settings-back-container"]}>
        <Button
          color={"primary"}
          variant={"text"}
          size={"medium"}
          onClick={close}
          icon={{ category: "outlined", type: "arrow_back", filled: true }}
        >
          {t("rework.back")}
        </Button>
      </span>
      <span className={styles["team-name"]}>{team.name}</span>
      <NavigationMenu items={navigationMenu}></NavigationMenu>
      <div className={styles["team-settings-navbar-disconnect"]}>
        <Button
          color={"error"}
          variant={"filled"}
          size={"medium"}
          icon={{ category: "outlined", type: "logout", filled: true }}
          disabled={true}
        >
          {t("rework.teamSettings.navigation.leaveTeam")}
        </Button>
      </div>
    </div>
  );
}
