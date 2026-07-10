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
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import {
  useCreateTeamMutation,
  useListUsersQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { UserSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AdminTeamsPage.module.css";

// AUTHZ-05 (RFC §28): team creation is a one-shot, platform-admin-gated
// bootstrap action — there is no other way to give a freshly created team its
// first team_admin. This is deliberately minimal: name + initial admin
// picker, nothing else.
export default function AdminTeamsPage() {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();

  const [name, setName] = useState("");
  const [selectedAdmins, setSelectedAdmins] = useState<UserSummary[]>([]);
  const [adminQuery, setAdminQuery] = useState("");

  const { data: allUsers } = useListUsersQuery();
  const [createTeam, { isLoading: isCreating }] = useCreateTeamMutation();

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
                    color="on-surface"
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
