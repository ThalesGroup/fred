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
import Switch from "@shared/atoms/Switch/Switch";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import { teamDescriptionText } from "@core/utils/teamFields.ts";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useUserCapabilities } from "@core/hooks/useUserCapabilities.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { getConfig } from "../../../../../common/config";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import PlatformAccessLinkManager from "../PlatformAccessPage/PlatformAccessLinkManager";
import {
  useDefaultTeamsForNewUsersQuery,
  useListAllTeamsQuery,
  useSetDefaultTeamsForNewUsersMutation,
  usePlatformAccessStateQuery,
  usePlatformAccessTeamsQuery,
  useSetPlatformTeamMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import TeamFormDialog from "./TeamFormDialog";
import styles from "./AdminTeamsPage.module.css";

// Registry edits and Platform Access controls have separate permissions.
export default function AdminTeamsPage() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();

  // `null`: closed; `"create"`: a new team; a team: that team's edit.
  const [teamForm, setTeamForm] = useState<Team | "create" | null>(null);
  // The admins column needs each team's roster.
  const { data: allTeams } = useListAllTeamsQuery({ includeMembership: true });

  const { canAdmin, canManageTeams, canManagePlatformAccess } = useUserCapabilities();
  const admissionEnabled = canManagePlatformAccess && (getConfig()?.platform_access_enabled ?? false);
  const admission = usePlatformAccessStateQuery(undefined, { skip: !admissionEnabled });
  const admissionTeams = usePlatformAccessTeamsQuery(undefined, { skip: !admissionEnabled });
  const [setAdmissionTeam, { isLoading: isSettingAdmissionTeam }] = useSetPlatformTeamMutation();
  const [linkTeam, setLinkTeam] = useState<string>();
  const accessTeams = useMemo(
    () => new Map((admissionTeams.data ?? []).map((team) => [team.team_id, team])),
    [admissionTeams.data],
  );
  const selectedLinkTeam = linkTeam ? accessTeams.get(linkTeam) : undefined;
  const admissionLocked =
    isSettingAdmissionTeam ||
    admission.isFetching ||
    admission.isError ||
    !admission.data ||
    admissionTeams.isFetching ||
    admissionTeams.isError;
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
        cellRenderer: (team) => {
          const description = teamDescriptionText(team, t);
          return (
            <div className={styles.teamNameCell}>
              <span className={styles.teamName}>{team.name}</span>
              {description && (
                <span className={styles.teamDescription} title={description}>
                  {description}
                </span>
              )}
            </div>
          );
        },
      },
      {
        label: t("rework.adminTeams.existingTeams.table.admins"),
        cellRenderer: (team) => {
          const admins = (team.admins ?? []).map((admin) => ({
            id: admin.id,
            name: `${admin.first_name} ${admin.last_name}`,
            imageUrl: admin.avatar_image_url,
          }));
          const pendingIds = new Set(team.pending_admin_ids ?? []);
          const pending = admins.filter((admin) => pendingIds.has(admin.id));
          return (
            <div className={styles.adminsCell}>
              <AvatarGroup avatars={admins.map(({ name, imageUrl }) => ({ name, imageUrl }))} />
              {pending.length > 0 && (
                <span
                  className={styles.pendingAdmins}
                  title={pending.map(({ name }) => t("rework.adminTeams.pendingAdminHint", { name })).join("\n")}
                >
                  {t("rework.adminTeams.existingTeams.pendingCount", { count: pending.length })}
                </span>
              )}
            </div>
          );
        },
      },
      ...(admissionEnabled
        ? [
            {
              label: t("rework.platformAccess.free"),
              size: "minmax(9rem, 1fr)",
              cellRenderer: (team: Team) => {
                const access = accessTeams.get(team.id);
                return (
                  <Switch
                    size="small"
                    aria-label={`${t("rework.platformAccess.free")} ${team.name}`}
                    checked={access?.free ?? false}
                    disabled={admissionLocked || !access}
                    onChange={(event) => {
                      if (!access || admissionLocked) return;
                      void runMutationAction({
                        action: () =>
                          setAdmissionTeam({
                            teamId: team.id,
                            setPlatformAccessTeam: { allowed: access.allowed, free: event.target.checked },
                          }).unwrap(),
                        onError: (error) =>
                          showError({
                            summary: t(
                              normalizeApiError(error).detail === "platform_access_actor_lockout"
                                ? "rework.platformAccess.actorLockout"
                                : "rework.platformAccess.failed",
                            ),
                          }),
                      });
                    }}
                  />
                );
              },
            },
            {
              label: t("rework.platformAccess.link"),
              size: "1.5fr",
              cellRenderer: (team: Team) => (
                <Button
                  color="primary"
                  variant="outlined"
                  size="small"
                  disabled={admissionLocked || !accessTeams.has(team.id)}
                  onClick={() => setLinkTeam(team.id)}
                >
                  {t("rework.platformAccess.links.manage")}
                </Button>
              ),
            },
          ]
        : []),
      ...(canAdmin
        ? [
            {
              label: "",
              // Cell padding plus the 40px medium button: narrower squeezes it into an oval.
              size: "4rem",
              cellRenderer: (team: Team) => (
                <IconButton
                  variant="icon"
                  size="medium"
                  color="on-surface-retreat"
                  icon={{ category: "outlined", type: "edit" }}
                  aria-label={t("rework.adminTeams.editTeam.openAria", { name: team.name })}
                  onClick={() => setTeamForm(team)}
                />
              ),
            },
          ]
        : []),
    ],
    [t, canAdmin, admissionEnabled, admissionLocked, accessTeams, runMutationAction, setAdmissionTeam, showError],
  );

  return (
    <div className={styles.adminTeamsPage}>
      <PageHeader
        title={t("rework.adminTeams.title")}
        actions={
          canManageTeams && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setTeamForm("create")}
            >
              {t("rework.adminTeams.createTeam.open")}
            </Button>
          )
        }
      />
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
      <section className={styles.existingTeamsSection}>
        <h2 className={styles.sectionTitle}>{t("rework.adminTeams.existingTeams.title")}</h2>
        {admissionEnabled && <p className={styles.sectionDescription}>{t("rework.platformAccess.freeHint")}</p>}
        {admissionEnabled && (admission.isError || admissionTeams.isError) && (
          <p role="alert">{t("rework.platformAccess.failed")}</p>
        )}
        {allTeams && allTeams.length > 0 ? (
          <DataTable columns={teamColumns} data={allTeams} />
        ) : (
          <p className={styles.emptyTeamsMessage}>{t("rework.adminTeams.existingTeams.empty")}</p>
        )}
      </section>
      {teamForm && (
        <TeamFormDialog team={teamForm === "create" ? undefined : teamForm} onClose={() => setTeamForm(null)} />
      )}
      {admissionEnabled && selectedLinkTeam && (
        <PlatformAccessLinkManager team={selectedLinkTeam} onClose={() => setLinkTeam(undefined)} />
      )}
    </div>
  );
}
