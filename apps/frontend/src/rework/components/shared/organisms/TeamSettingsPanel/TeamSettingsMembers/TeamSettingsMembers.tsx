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
import TeamSettingsMembersMenu from "./TeamSettingsMembersMenu/TeamSettingsMembersMenu.tsx";
import AddTeamMembersDialog from "./AddTeamMembersDialog/AddTeamMembersDialog.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import TeamInviteLinkDialog from "./TeamInviteLinkDialog/TeamInviteLinkDialog.tsx";
import TeamJoinRequestsSection from "./TeamJoinRequestsSection/TeamJoinRequestsSection.tsx";
import { getConfig } from "../../../../../../common/config";
import styles from "./TeamSettingsMembers.module.scss";

interface TeamSettingsMembersProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsMembers({ team }: TeamSettingsMembersProps) {
  const { t } = useTranslation();

  const { canAdministerMembers: can_administer_members } = useTeamCapabilities(team);

  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [isInviteLinkOpen, setIsInviteLinkOpen] = useState(false);
  // Invite links live in platform access, only available on deployments that enable it.
  const canShareInviteLink = can_administer_members && (getConfig()?.platform_access_enabled ?? false);
  const [search, setSearch] = useState("");

  return (
    <div className={styles["team-settings-members-container"]}>
      <PageHeader
        title={t("rework.teamSettings.members.title")}
        titleAction={<TeamSettingsMembersMenu team={team} />}
        actions={
          <>
            <div className={styles["team-settings-members-search"]}>
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder={t("rework.teamSettings.members.search.placeholder")}
                ariaLabel={t("rework.teamSettings.members.search.ariaLabel")}
                clearAriaLabel={t("rework.teamSettings.members.search.clearAriaLabel")}
                size="small"
              />
            </div>
            {canShareInviteLink && (
              <Button color="primary" variant="outlined" size="medium" onClick={() => setIsInviteLinkOpen(true)}>
                {t("rework.teamSettings.members.inviteLink.buttonLabel")}
              </Button>
            )}
            {can_administer_members && (
              <Button color="primary" variant="filled" size="medium" onClick={() => setIsAddDialogOpen(true)}>
                {t("rework.teamSettings.members.addMembersDialog.buttonLabel")}
              </Button>
            )}
          </>
        }
      />
      <TeamJoinRequestsSection
        teamId={team.id}
        canAdministerMembers={can_administer_members}
        takesRequests={team.visibility === "public" && team.joining_mode === "on_request"}
      />
      <div className={styles["team-settings-members-table-wrapper"]}>
        <TeamSettingsMembersTable team={team} search={search} />
      </div>
      {can_administer_members && (
        <AddTeamMembersDialog open={isAddDialogOpen} team={team} onClose={() => setIsAddDialogOpen(false)} />
      )}
      {canShareInviteLink && isInviteLinkOpen && (
        <TeamInviteLinkDialog teamId={team.id} onClose={() => setIsInviteLinkOpen(false)} />
      )}
    </div>
  );
}
