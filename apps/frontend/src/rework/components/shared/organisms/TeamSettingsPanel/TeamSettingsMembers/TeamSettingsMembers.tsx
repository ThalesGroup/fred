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
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions, UserSummary } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAddTeamMemberMutation,
  useSearchCandidateTeamMembersQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import styles from "./TeamSettingsMembers.module.scss";

interface TeamSettingsMembersProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsMembers({ team }: TeamSettingsMembersProps) {
  const { t } = useTranslation();

  const { canAdministerMembers: can_administer_members } = useTeamCapabilities(team);

  const [addTeamMember, { isLoading: isAddingMember }] = useAddTeamMemberMutation();

  const [addUserQuery, setAddUserQuery] = useState<string>("");
  const trimmedQuery = addUserQuery.trim();

  const { data: suggestions = [] } = useSearchCandidateTeamMembersQuery(
    { teamId: team.id, query: trimmedQuery },
    { skip: !can_administer_members || trimmedQuery.length < 2 },
  );

  const handleAddMember = async (user: UserSummary) => {
    if (isAddingMember) return;
    await addTeamMember({
      teamId: team.id,
      addTeamMemberRequest: { user_id: user.id, relation: "team_member" },
    });
    setAddUserQuery("");
  };
  return (
    <div className={styles["team-settings-members-container"]}>
      <div className={styles["team-settings-members-header"]}>
        <div className={styles["team-settings-members-header-title"]}>{t("rework.teamSettings.members.title")}</div>
        {can_administer_members && (
          <Autocomplete<UserSummary>
            textInput={{
              placeholder: t("rework.teamSettings.members.addMember.placeholder"),
              icon: { category: "outlined", type: "search" },
            }}
            onFieldValueChange={setAddUserQuery}
            options={suggestions.map((user) => ({
              label: `${user.first_name} ${user.last_name} (${user.username})`,
              value: user,
              key: user.id,
            }))}
            onSelect={handleAddMember}
          ></Autocomplete>
        )}
      </div>
      <TeamSettingsMembersTable team={team} />
    </div>
  );
}
