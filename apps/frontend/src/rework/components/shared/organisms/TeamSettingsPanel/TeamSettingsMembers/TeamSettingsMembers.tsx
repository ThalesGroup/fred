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

import TeamSettingsMembersTable from "./TeamSettingsMembersTable/TeamSettingsMembersTable.tsx";
import LeaveTeamButton from "./LeaveTeamButton/LeaveTeamButton.tsx";
import AddTeamMembersDialog from "./AddTeamMembersDialog/AddTeamMembersDialog.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import styles from "./TeamSettingsMembers.module.scss";

interface TeamSettingsMembersProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsMembers({ team }: TeamSettingsMembersProps) {
  const { t } = useTranslation();

  const { canAdministerMembers: can_administer_members } = useTeamCapabilities(team);

  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  return (
    <div className={styles["team-settings-members-container"]}>
      <div className={styles["team-settings-members-header"]}>
        <div className={styles["team-settings-members-header-left"]}>
          <div className={styles["team-settings-members-header-title"]}>{t("rework.teamSettings.members.title")}</div>
          <LeaveTeamButton team={team} />
        </div>
        {can_administer_members && (
          <Button color="primary" variant="filled" size="medium" onClick={() => setIsAddDialogOpen(true)}>
            {t("rework.teamSettings.members.addMembersDialog.buttonLabel")}
          </Button>
        )}
      </div>
      <div className={styles["team-settings-members-table-wrapper"]}>
        <TeamSettingsMembersTable team={team} />
      </div>
      {can_administer_members && (
        <AddTeamMembersDialog open={isAddDialogOpen} team={team} onClose={() => setIsAddDialogOpen(false)} />
      )}
    </div>
  );
}
