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

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import AvatarGroup from "@shared/molecules/AvatarGroup/AvatarGroup.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import {
  useCreateTeamMutation,
  useDeleteTeamMutation,
  useListAllTeamsQuery,
  useListUsersQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Team, UserSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AdminTeamsPage.module.css";

// AUTHZ-05 (RFC §28): team creation is a one-shot, platform-admin-gated
// bootstrap action — there is no other way to give a freshly created team its
// first team_admin. Deletion is the same kind of registry-level action
// (`can_delete_team`): it drops the registry entry and every relation pointing
// at the team, so it always goes through a critical-action confirmation.
export default function AdminTeamsPage() {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [name, setName] = useState("");
  const [selectedAdmins, setSelectedAdmins] = useState<UserSummary[]>([]);
  const [adminQuery, setAdminQuery] = useState("");

  const { data: allUsers } = useListUsersQuery();
  const { data: allTeams } = useListAllTeamsQuery();
  const [createTeam, { isLoading: isCreating }] = useCreateTeamMutation();
  const [deleteTeam] = useDeleteTeamMutation();

  const handleDelete = useCallback(
    (team: Team) => {
      showConfirmationDialog({
        criticalAction: true,
        title: t("rework.adminTeams.deleteTeam.dialogTitle", { name: team.name }),
        message: t("rework.adminTeams.deleteTeam.dialogMessage", { name: team.name }),
        confirmButtonLabel: t("rework.adminTeams.deleteTeam.confirm"),
        cancelButtonLabel: t("rework.adminTeams.deleteTeam.cancel"),
        onConfirm: () =>
          void runMutationAction({
            action: () => deleteTeam({ teamId: team.id }).unwrap(),
            onSuccess: () => showSuccess({ summary: t("rework.adminTeams.deleteTeam.successSummary") }),
            onError: (error) =>
              notifyApiError(error, {
                summary: t("rework.adminTeams.deleteTeam.errors.summary"),
                fallbackDetail: t("rework.adminTeams.deleteTeam.errors.fallbackDetail"),
                forbiddenDetail: t("rework.adminTeams.deleteTeam.errors.forbiddenDetail"),
              }),
          }),
      });
    },
    [showConfirmationDialog, runMutationAction, deleteTeam, showSuccess, notifyApiError, t],
  );

  const teamColumns = useMemo(
    (): DataTableColumn<Team>[] => [
      {
        label: t("rework.adminTeams.existingTeams.table.name"),
        size: "2fr",
        cellRenderer: (team) => <span>{team.name}</span>,
      },
      {
        label: t("rework.adminTeams.existingTeams.table.admins"),
        cellRenderer: (team) => (
          <AvatarGroup
            avatars={(team.admins ?? []).map((admin) => ({ name: `${admin.first_name} ${admin.last_name}` }))}
          />
        ),
      },
      {
        // Fixed track, not "auto": the header is empty while the cell holds an
        // icon button, and DataTable resolves header and body tracks separately.
        label: "",
        size: "3rem",
        cellRenderer: (team) => (
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "delete" }}
            aria-label={t("rework.adminTeams.deleteTeam.action", { name: team.name })}
            onClick={() => handleDelete(team)}
          />
        ),
      },
    ],
    [t, handleDelete],
  );

  const suggestions = useMemo(() => {
    if (!allUsers) return [];
    const selectedIds = new Set(selectedAdmins.map((u) => u.id));
    const query = adminQuery.toLowerCase().trim();
    return allUsers
      .filter((u) => !selectedIds.has(u.id))
      .filter((u) => !query || `${u.first_name} ${u.last_name} ${u.username}`.toLowerCase().includes(query));
  }, [allUsers, selectedAdmins, adminQuery]);

  const handleSelectAdmin = (user: UserSummary) => {
    setSelectedAdmins((prev) => [...prev, user]);
    setAdminQuery("");
  };

  const handleRemoveAdmin = (userId: string) => {
    setSelectedAdmins((prev) => prev.filter((u) => u.id !== userId));
  };

  const canSubmit = name.trim().length > 0 && selectedAdmins.length > 0 && !isCreating;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    await runMutationAction({
      action: () =>
        createTeam({
          createTeamRequest: {
            name: name.trim(),
            initial_team_admin_ids: selectedAdmins.map((u) => u.id),
          },
        }).unwrap(),
      onSuccess: () => {
        showSuccess({ summary: t("rework.adminTeams.createTeam.successSummary") });
        setName("");
        setSelectedAdmins([]);
      },
      onError: (error) =>
        notifyApiError(error, {
          summary: t("rework.adminTeams.createTeam.errors.summary"),
          fallbackDetail: t("rework.adminTeams.createTeam.errors.fallbackDetail"),
          forbiddenDetail: t("rework.adminTeams.createTeam.errors.forbiddenDetail"),
          conflictDetail: t("rework.adminTeams.createTeam.errors.conflictDetail"),
        }),
    });
  };

  return (
    <div className={styles.adminTeamsPage}>
      <PageHeader title={t("rework.adminTeams.title")} />
      <section className={styles.existingTeamsSection}>
        <h2 className={styles.sectionTitle}>{t("rework.adminTeams.existingTeams.title")}</h2>
        {allTeams && allTeams.length > 0 ? (
          <DataTable columns={teamColumns} data={allTeams} />
        ) : (
          <p className={styles.emptyTeamsMessage}>{t("rework.adminTeams.existingTeams.empty")}</p>
        )}
      </section>
      <Separator />
      <section className={styles.createTeamSection}>
        <h2 className={styles.sectionTitle}>{t("rework.adminTeams.createTeam.title")}</h2>
        <TextInput
          label={t("rework.adminTeams.createTeam.nameLabel")}
          placeholder={t("rework.adminTeams.createTeam.namePlaceholder")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <div className={styles.adminsField}>
          <span className={styles.adminsLabel}>{t("rework.adminTeams.createTeam.adminsLabel")} *</span>
          <Autocomplete<UserSummary>
            textInput={{
              placeholder: t("rework.adminTeams.createTeam.adminsPlaceholder"),
              icon: { category: "outlined", type: "search" },
            }}
            onFieldValueChange={setAdminQuery}
            options={suggestions.map((user) => ({
              label: `${user.first_name} ${user.last_name} (${user.username})`,
              value: user,
              key: user.id,
            }))}
            onSelect={handleSelectAdmin}
          />
          {selectedAdmins.length > 0 && (
            <ul className={styles.adminChipList}>
              {selectedAdmins.map((user) => (
                <li key={user.id} className={styles.adminChip}>
                  <span>{`${user.first_name} ${user.last_name}`}</span>
                  <IconButton
                    variant="icon"
                    size="small"
                    icon={{ category: "outlined", type: "close" }}
                    onClick={() => handleRemoveAdmin(user.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className={styles.actions}>
          <Button color="primary" variant="filled" size="medium" disabled={!canSubmit} onClick={handleSubmit}>
            {t("rework.adminTeams.createTeam.submit")}
          </Button>
        </div>
      </section>
    </div>
  );
}
