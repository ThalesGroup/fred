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

import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { OptionModel } from "@models/Option.model.ts";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import DataTable, { DataTableColumn } from "@shared/organisms/DataTable/DataTable.tsx";
import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  TeamMember,
  TeamWithPermissions,
  useListTeamMembersQuery,
  useRemoveTeamMemberMutation,
  UserTeamRelation,
  useUpdateTeamMemberMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApi.ts";

const TEAM_ROLES: UserTeamRelation[] = ["owner", "manager", "member"];
const ROLE_PRIORITY: Record<UserTeamRelation, number> = {
  owner: 0,
  manager: 1,
  member: 2,
};

function compareStrings(valA: string | null | undefined, valB: string | null | undefined): number {
  if (!valA && !valB) return 0;
  if (!valA) return 1;
  if (!valB) return -1;
  return valA.localeCompare(valB);
}

interface TeamSettingsMembersTableProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsMembersTable({ team }: TeamSettingsMembersTableProps) {
  const { t } = useTranslation();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();

  const { data: teamMembers } = useListTeamMembersQuery({ teamId: team.id });
  const [updateTeamMember] = useUpdateTeamMemberMutation();
  const [removeTeamMember] = useRemoveTeamMemberMutation();

  const can_administer_members = team.permissions?.includes("can_administer_members");
  const can_administer_managers = team.permissions?.includes("can_administer_managers");
  const can_administer_owners = team.permissions?.includes("can_administer_owners");

  const can_administer_anyone = can_administer_members || can_administer_managers || can_administer_owners;

  function getAdministerPermissionForTeamRole(target: UserTeamRelation): boolean | undefined {
    if (target === "manager") return can_administer_managers;
    if (target === "owner") return can_administer_owners;
    return can_administer_members;
  }

  const handleRoleChange = useCallback(
    async (userId: string, newRelation: UserTeamRelation) => {
      await runMutationAction({
        action: () =>
          updateTeamMember({
            teamId: team.id,
            userId,
            updateTeamMemberRequest: { relation: newRelation },
          }).unwrap(),
        onError: (error) =>
          notifyApiError(error, {
            summary: t("rework.teamSettings.members.errors.updateRoleSummary", {
              defaultValue: "Failed to update role",
            }),
            fallbackDetail: t("rework.teamSettings.members.errors.updateRoleDetail", {
              defaultValue: "Could not update member role.",
            }),
            forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail", {
              defaultValue: "You are not allowed to change this role.",
            }),
            conflictDetail: t("rework.teamSettings.members.errors.lastOwnerDetail", {
              defaultValue: "A team must keep at least one owner.",
            }),
          }),
      });
    },
    [runMutationAction, updateTeamMember, team.id, notifyApiError, t],
  );

  const handleRemoveMember = useCallback(
    async (userId: string) => {
      await runMutationAction({
        action: () =>
          removeTeamMember({
            teamId: team.id,
            userId,
          }).unwrap(),
        onError: (error) =>
          notifyApiError(error, {
            summary: t("rework.teamSettings.members.errors.removeMemberSummary", {
              defaultValue: "Failed to remove member",
            }),
            fallbackDetail: t("rework.teamSettings.members.errors.removeMemberDetail", {
              defaultValue: "Could not remove team member.",
            }),
            forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail", {
              defaultValue: "You are not allowed to remove this member.",
            }),
            conflictDetail: t("rework.teamSettings.members.errors.lastOwnerDetail", {
              defaultValue: "A team must keep at least one owner.",
            }),
          }),
      });
    },
    [runMutationAction, removeTeamMember, team.id, notifyApiError, t],
  );

  const sortedMembers = useMemo(() => {
    return (
      teamMembers?.slice().sort((a, b) => {
        const roleDiff = ROLE_PRIORITY[a.relation] - ROLE_PRIORITY[b.relation];
        if (roleDiff !== 0) return roleDiff;

        return (
          compareStrings(a.user.last_name, b.user.last_name) ||
          compareStrings(a.user.first_name, b.user.first_name) ||
          compareStrings(a.user.username, b.user.username)
        );
      }) || []
    );
  }, [teamMembers]);

  const columns = useMemo((): DataTableColumn<TeamMember>[] => {
    const cols: DataTableColumn<TeamMember>[] = [
      {
        label: t("rework.teamSettings.members.table.identifiant"),
        cellRenderer: (teamMember) => <div>{teamMember.user.username}</div>,
      },
      {
        label: t("rework.teamSettings.members.table.firstName"),
        cellRenderer: (teamMember) => <div>{teamMember.user.first_name}</div>,
      },
      {
        label: t("rework.teamSettings.members.table.lastName"),
        cellRenderer: (teamMember) => <div>{teamMember.user.last_name}</div>,
      },
      {
        label: t("rework.teamSettings.members.table.role"),
        cellRenderer: (teamMember) => {
          const can_administer_this_member = getAdministerPermissionForTeamRole(teamMember.relation);

          const roleSelectedOption = TEAM_ROLES.map(
            (role): OptionModel => ({
              label: t(`rework.teamRoles.${role}`),
              value: role,
              key: role,
            }),
          );
          return can_administer_this_member ? (
            <Select
              options={roleSelectedOption}
              value={teamMember.relation}
              onChange={function (value: UserTeamRelation): void {
                handleRoleChange(teamMember.user.id, value);
              }}
              compact={true}
              size={"medium"}
            ></Select>
          ) : (
            <div>{teamMember.relation}</div>
          );
        },
      },
    ];
    if (can_administer_anyone) {
      cols.push({
        label: t("rework.teamSettings.members.table.actions"),
        size: "6rem",
        cellRenderer: (teamMember) => (
          <IconButtonMenu<"DELETE">
            iconButton={{
              color: "on-surface",
              variant: "icon",
              size: "medium",
              icon: { category: "outlined", type: "more_horiz" },
            }}
            options={[
              {
                icon: { category: "outlined", type: "delete" },
                label: t("rework.teamSettings.members.table.deleteAction"),
                value: "DELETE",
                key: "DELETE",
              },
            ]}
            onSelect={(_) => {
              handleRemoveMember(teamMember.user.id);
            }}
          />
        ),
      });
    }
    return cols;
  }, [
    t,
    can_administer_anyone,
    can_administer_managers,
    can_administer_owners,
    can_administer_members,
    handleRoleChange,
    handleRemoveMember,
  ]);

  return <DataTable columns={columns} data={sortedMembers} />;
}
