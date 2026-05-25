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

import styles from "./TeamSettingsNavbar.module.scss";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import Button from "@shared/atoms/Button/Button.tsx";
import { TeamSettingsMenuPanels } from "../TeamSettingsPanel.tsx";

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
      <span className={styles["team-name"]}>
        {team.id === "personal" ? t("rework.sidebar.team.userTeam") : team.name}
      </span>
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
