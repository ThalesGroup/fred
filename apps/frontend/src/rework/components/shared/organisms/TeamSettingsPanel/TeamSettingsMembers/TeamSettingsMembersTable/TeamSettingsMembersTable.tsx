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
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  TeamMember,
  TeamWithPermissions,
  UserTeamRelation,
} from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useGrantTeamMemberRoleMutation,
  useListTeamMembersQuery,
  useRemoveTeamMemberMutation,
  useRevokeTeamMemberRoleMutation,
} from "../../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import styles from "./TeamSettingsMembersTable.module.scss";

// AUTHZ-06 (RFC Part 7 §34): a member may hold several of these at once (e.g.
// a small team's sole admin who is also its editor and analyst) — each is
// granted/revoked as its own independent, permission-checked action, never a
// bulk role-set replace. `team_member` is deliberately excluded: it is the
// implicit baseline when none of the three apply, not a toggle of its own.
const ELEVATED_ROLES: UserTeamRelation[] = ["team_admin", "team_editor", "team_analyst"];
const ROLE_PRIORITY: Record<UserTeamRelation, number> = {
  team_admin: 0,
  team_editor: 1,
  team_analyst: 2,
  team_member: 3,
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
  const [grantTeamMemberRole] = useGrantTeamMemberRoleMutation();
  const [revokeTeamMemberRole] = useRevokeTeamMemberRoleMutation();
  const [removeTeamMember] = useRemoveTeamMemberMutation();

  const {
    canAdministerMembers: can_administer_members,
    canAdministerEditors: can_administer_editors,
    canAdministerAnalysts: can_administer_analysts,
    canAdministerAdmins: can_administer_admins,
  } = useTeamCapabilities(team);

  const can_administer_anyone =
    can_administer_members || can_administer_editors || can_administer_analysts || can_administer_admins;

  function getAdministerPermissionForTeamRole(target: UserTeamRelation): boolean | undefined {
    if (target === "team_editor") return can_administer_editors;
    if (target === "team_analyst") return can_administer_analysts;
    if (target === "team_admin") return can_administer_admins;
    return can_administer_members;
  }

  const handleGrantRole = useCallback(
    async (userId: string, relation: UserTeamRelation) => {
      await runMutationAction({
        action: () =>
          grantTeamMemberRole({
            teamId: team.id,
            userId,
            grantTeamMemberRoleRequest: { relation },
          }).unwrap(),
        onError: (error) =>
          notifyApiError(error, {
            summary: t("rework.teamSettings.members.errors.updateRoleSummary", {}),
            fallbackDetail: t("rework.teamSettings.members.errors.updateRoleDetail", {}),
            forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail", {}),
            conflictDetail: t("rework.teamSettings.members.errors.lastOwnerDetail", {}),
          }),
      });
    },
    [runMutationAction, grantTeamMemberRole, team.id, notifyApiError, t],
  );

  const handleRevokeRole = useCallback(
    async (userId: string, relation: UserTeamRelation) => {
      await runMutationAction({
        action: () => revokeTeamMemberRole({ teamId: team.id, userId, relation }).unwrap(),
        onError: (error) =>
          notifyApiError(error, {
            summary: t("rework.teamSettings.members.errors.updateRoleSummary", {}),
            fallbackDetail: t("rework.teamSettings.members.errors.updateRoleDetail", {}),
            forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail", {}),
            conflictDetail: t("rework.teamSettings.members.errors.lastOwnerDetail", {}),
          }),
      });
    },
    [runMutationAction, revokeTeamMemberRole, team.id, notifyApiError, t],
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
            summary: t("rework.teamSettings.members.errors.removeMemberSummary", {}),
            fallbackDetail: t("rework.teamSettings.members.errors.removeMemberDetail", {}),
            forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail", {}),
            conflictDetail: t("rework.teamSettings.members.errors.lastOwnerDetail", {}),
          }),
      });
    },
    [runMutationAction, removeTeamMember, team.id, notifyApiError, t],
  );

  const sortedMembers = useMemo(() => {
    return (
      teamMembers?.slice().sort((a, b) => {
        const roleDiff =
          Math.min(...a.relations.map((r) => ROLE_PRIORITY[r])) - Math.min(...b.relations.map((r) => ROLE_PRIORITY[r]));
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
        size: "1.5fr",
        cellRenderer: (teamMember) => (
          <div className={styles.roleChips} role="group">
            {ELEVATED_ROLES.map((role) => {
              const held = teamMember.relations.includes(role);
              const canAdminister = Boolean(getAdministerPermissionForTeamRole(role));
              return (
                <button
                  key={role}
                  type="button"
                  className={styles.roleChip}
                  data-active={held}
                  aria-pressed={held}
                  disabled={!canAdminister}
                  onClick={() =>
                    held ? handleRevokeRole(teamMember.user.id, role) : handleGrantRole(teamMember.user.id, role)
                  }
                >
                  {t(`rework.teamRoles.${role}`)}
                </button>
              );
            })}
          </div>
        ),
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
    can_administer_editors,
    can_administer_analysts,
    can_administer_admins,
    can_administer_members,
    handleGrantRole,
    handleRevokeRole,
    handleRemoveMember,
  ]);

  return <DataTable columns={columns} data={sortedMembers} />;
}
