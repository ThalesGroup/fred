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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import AvatarGroup from "@shared/molecules/AvatarGroup/AvatarGroup.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useUserCapabilities } from "@core/hooks/useUserCapabilities.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import {
  useCreateTeamMutation,
  useDefaultTeamsForNewUsersQuery,
  useListAllTeamsQuery,
  useSearchCandidateTeamAdminsQuery,
  useSetDefaultTeamsForNewUsersMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Team, UserSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AdminTeamsPage.module.css";

// AUTHZ-05 (RFC §28): team creation is a one-shot bootstrap action — there is
// no other way to give a freshly created team its first team_admin. Every call
// this page fires is reachable by a `team_manager` who is not a platform_admin
// (`can_create_team` / `can_list_all_teams`); the existing-teams list is a
// read-only registry view, and delete/rescue stay platform_admin-only and have
// no affordance here.
export default function AdminTeamsPage() {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();

  const [name, setName] = useState("");
  const [selectedAdmins, setSelectedAdmins] = useState<UserSummary[]>([]);
  const [adminQuery, setAdminQuery] = useState("");

  // Server-side search, not the org-wide `GET /users` listing: that one is
  // gated on `can_administer_users` (platform_admin only), so a team_manager
  // reached this page and found the admin picker permanently empty.
  const trimmedAdminQuery = adminQuery.trim();
  const { data: candidateAdmins } = useSearchCandidateTeamAdminsQuery(
    { query: trimmedAdminQuery },
    { skip: trimmedAdminQuery.length < 2 },
  );
  // The admins column needs each team's roster.
  const { data: allTeams } = useListAllTeamsQuery({ includeMembership: true });
  const [createTeam, { isLoading: isCreating }] = useCreateTeamMutation();

  // Choosing where new users land is platform_admin-only, unlike the rest of this page.
  const { canAdmin } = useUserCapabilities();
  // Membership is granted on GCU acceptance: without GCU the setting never applies.
  const { gcuVersion } = useFrontendProperties();
  const [setDefaultTeams, { isLoading: isSettingDefaultTeams }] = useSetDefaultTeamsForNewUsersMutation();
  const [defaultTeamQuery, setDefaultTeamQuery] = useState("");
  const { data: defaultTeams } = useDefaultTeamsForNewUsersQuery(undefined, { skip: !canAdmin });

  // Filtered client-side: the registry listing is already loaded for the table.
  const defaultTeamOptions = useMemo(() => {
    const query = defaultTeamQuery.trim().toLowerCase();
    const defaultIds = new Set((defaultTeams ?? []).map((team) => team.team_id));
    return (allTeams ?? [])
      .filter((team) => !defaultIds.has(team.id) && team.name.toLowerCase().includes(query))
      .map((team) => ({ label: team.name, value: team, key: team.id }));
  }, [allTeams, defaultTeams, defaultTeamQuery]);

  // The PUT replaces the whole list, so every change sends the teams it keeps.
  const saveDefaultTeams = (teamIds: string[]) =>
    runMutationAction({
      action: () => setDefaultTeams({ setDefaultTeamsForNewUsersRequest: { team_ids: teamIds } }).unwrap(),
      onSuccess: () => showSuccess({ summary: t("rework.adminTeams.defaultTeam.savedSummary") }),
      onError: (error) =>
        notifyApiError(error, {
          summary: t("rework.adminTeams.defaultTeam.errors.summary"),
          fallbackDetail: t("rework.adminTeams.defaultTeam.errors.fallbackDetail"),
        }),
    });
  const defaultTeamIds = (defaultTeams ?? []).map((team) => team.team_id);
  const handleAddDefaultTeam = (team: Team) => saveDefaultTeams([...defaultTeamIds, team.id]);
  const handleRemoveDefaultTeam = (teamId: string) => saveDefaultTeams(defaultTeamIds.filter((id) => id !== teamId));

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
    ],
    [t],
  );

  const suggestions = useMemo(() => {
    if (!candidateAdmins) return [];
    const selectedIds = new Set(selectedAdmins.map((u) => u.id));
    return candidateAdmins.filter((u) => !selectedIds.has(u.id));
  }, [candidateAdmins, selectedAdmins]);

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
      {/* Actions first: the registry list grows long and pushed them out of reach. */}
      {canAdmin && (
        <>
          <section className={styles.defaultTeamSection}>
            <h2 className={styles.sectionTitle}>{t("rework.adminTeams.defaultTeam.title")}</h2>
            <p className={styles.sectionDescription}>{t("rework.adminTeams.defaultTeam.description")}</p>
            {!gcuVersion && (
              <p className={styles.sectionDescription}>{t("rework.adminTeams.defaultTeam.gcuDisabled")}</p>
            )}
            <Autocomplete<Team>
              textInput={{
                placeholder: t("rework.adminTeams.defaultTeam.searchPlaceholder"),
                icon: { category: "outlined", type: "search" },
                // Adding before the current list is known would drop the teams already set.
                disabled: isSettingDefaultTeams || defaultTeams === undefined,
              }}
              onFieldValueChange={setDefaultTeamQuery}
              options={defaultTeamOptions}
              onSelect={handleAddDefaultTeam}
            />
            {defaultTeams && defaultTeams.length > 0 ? (
              <ul className={styles.adminChipList}>
                {defaultTeams.map((team) => (
                  <li key={team.team_id}>
                    <Chip
                      label={team.name}
                      // No remove while a save is in flight, so two removals never race.
                      onRemove={isSettingDefaultTeams ? undefined : () => handleRemoveDefaultTeam(team.team_id)}
                      removeAriaLabel={t("rework.adminTeams.defaultTeam.remove", { name: team.name })}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              // `undefined` while loading or on error: only the server's empty list means none.
              defaultTeams?.length === 0 && (
                <p className={styles.emptyTeamsMessage}>{t("rework.adminTeams.defaultTeam.none")}</p>
              )
            )}
          </section>
          <Separator />
        </>
      )}
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
                <li key={user.id}>
                  <Chip label={`${user.first_name} ${user.last_name}`} onRemove={() => handleRemoveAdmin(user.id)} />
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
      <Separator />
      <section className={styles.existingTeamsSection}>
        <h2 className={styles.sectionTitle}>{t("rework.adminTeams.existingTeams.title")}</h2>
        {allTeams && allTeams.length > 0 ? (
          <DataTable columns={teamColumns} data={allTeams} />
        ) : (
          <p className={styles.emptyTeamsMessage}>{t("rework.adminTeams.existingTeams.empty")}</p>
        )}
      </section>
    </div>
  );
}
