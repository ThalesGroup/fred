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

import styles from "./TeamSettingsPage.module.scss";
import { ModalInteractionProps } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import TeamSettingsNavbar from "@components/pages/TeamSettingsPage/TeamSettingsNavbar/TeamSettingsNavbar.tsx";
import { TeamWithPermissions } from "../../../../slices/controlPlane/controlPlaneOpenApi";
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
