import TeamSettingsMembersTable from "@components/pages/TeamSettingsPage/TeamSettingsMembers/TeamSettingsMembersTable/TeamSettingsMembersTable.tsx";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions, UserSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAddTeamMemberMutation,
  useListTeamMembersQuery,
  useListUsersQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamSettingsMembers.module.scss";

interface TeamSettingsMembersProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsMembers({ team }: TeamSettingsMembersProps) {
  const { t } = useTranslation();

  const can_administer_members = team.permissions?.includes("can_administer_members");

  const { data: teamMembers } = useListTeamMembersQuery({ teamId: team.id });
  const { data: allApplicationUsers } = useListUsersQuery();
  const [addTeamMember, { isLoading: isAddingMember }] = useAddTeamMemberMutation();

  const [addUserQuery, setAddUserQuery] = useState<string>("");

  const availableUsers = useMemo(() => {
    if (!allApplicationUsers) return [];
    if (!teamMembers) return allApplicationUsers;

    const memberIds = new Set(teamMembers.map((m) => m.user.id));
    return allApplicationUsers.filter((u) => !memberIds.has(u.id));
  }, [allApplicationUsers, teamMembers]);

  const suggestions = useMemo(() => {
    const query = addUserQuery.toLowerCase().trim();
    if (!query) return availableUsers;

    return availableUsers.filter((u) => `${u.first_name} ${u.last_name} ${u.username}`.toLowerCase().includes(query));
  }, [addUserQuery, availableUsers]);

  const handleAddMember = async (user: UserSummary) => {
    if (isAddingMember) return;
    await addTeamMember({
      teamId: team.id,
      addTeamMemberRequest: { user_id: user.id, relation: "member" },
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
