import styles from "./TeamSettingsPage.module.scss";
import { ModalInteractionProps } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import TeamSettingsNavbar from "@components/pages/TeamSettingsPage/TeamSettingsNavbar/TeamSettingsNavbar.tsx";
import { TeamWithPermissions } from "../../../../slices/controlPlane/controlPlaneApi.ts";
import TeamSettingsMembers from "@components/pages/TeamSettingsPage/TeamSettingsMembers/TeamSettingsMembers.tsx";
import { useState } from "react";
import TeamSettingsParameters from "@components/pages/TeamSettingsPage/TeamSettingsParameters/TeamSettingsParameters.tsx";

interface TeamSettingsPageProps {
  modalInteraction: ModalInteractionProps;
  team: TeamWithPermissions;
}

export default function TeamSettingsPage({ modalInteraction, team }: TeamSettingsPageProps) {
  const [settingsPanelSelection, setSettingsPanelSelection] = useState<TeamSettingsMenuPanels>(
    TeamSettingsMenuPanels.MEMBERS,
  );

  const renderContent = () => {
    switch (settingsPanelSelection) {
      case TeamSettingsMenuPanels.MEMBERS:
        return <TeamSettingsMembers team={team} />;
      case TeamSettingsMenuPanels.PARAMETERS:
        return <TeamSettingsParameters team={team} />;
      default:
        return null;
    }
  };

  return (
    <>
      <div className={styles["team-settings-page"]}>
        <TeamSettingsNavbar
          team={team}
          close={modalInteraction.close}
          changePanel={(panel) => setSettingsPanelSelection(panel)}
          panelSelected={settingsPanelSelection}
        ></TeamSettingsNavbar>
        {renderContent()}
      </div>
    </>
  );
}

export enum TeamSettingsMenuPanels {
  MEMBERS = "Members",
  PARAMETERS = "Parameters",
}
