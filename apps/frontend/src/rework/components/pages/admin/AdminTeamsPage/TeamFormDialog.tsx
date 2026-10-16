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
import Chip from "@shared/atoms/Chip/Chip.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import {
  MAX_TEAM_NAME_LENGTH,
  TEAM_DESCRIPTION_MAX_LENGTH,
  TEAM_DESCRIPTION_MIN_LENGTH,
  isValidTeamDescription,
} from "@core/utils/teamFields.ts";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import {
  useCreateTeamMutation,
  useEditTeamRegistryMutation,
  useSearchCandidateTeamAdminsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  EditTeamRegistryRequest,
  Team,
  UserSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AdminTeamsPage.module.css";

// The server's `detail` is English: these refusals show our own wording instead.
const REFUSAL_KEYS: Record<string, string> = {
  team_name_taken: "rework.adminTeams.refusals.teamNameTaken",
  team_last_admin: "rework.adminTeams.refusals.lastActiveAdmin",
  team_admin_pending_charter: "rework.adminTeams.refusals.pendingCharter",
};

interface TeamFormDialogProps {
  /** The team to edit; absent to create one. */
  team?: Team;
  onClose: () => void;
}

/** Create or edit a team's name, description and admins. An edit sends only what changed. */
export default function TeamFormDialog({ team, onClose }: TeamFormDialogProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const mode = team ? "edit" : "create";
  const keys = `rework.adminTeams.${mode}Team`;

  // The default description is not something an admin wrote: start empty.
  const storedDescription = team && !team.description_is_placeholder ? (team.description ?? "") : "";
  const initialAdmins = useMemo(() => team?.admins ?? [], [team]);
  const pendingAdminIds = useMemo(() => new Set(team?.pending_admin_ids ?? []), [team]);
  const [name, setName] = useState(team?.name ?? "");
  const [description, setDescription] = useState(storedDescription);
  // The minimum is only reported once the field has been left.
  const [descriptionTouched, setDescriptionTouched] = useState(false);
  const [admins, setAdmins] = useState<UserSummary[]>(initialAdmins);
  const [adminQuery, setAdminQuery] = useState("");

  const trimmedAdminQuery = adminQuery.trim();
  const { data: candidateAdmins } = useSearchCandidateTeamAdminsQuery(
    { query: trimmedAdminQuery },
    { skip: trimmedAdminQuery.length < 2 },
  );
  const [createTeam, { isLoading: isCreating }] = useCreateTeamMutation();
  const [editTeam, { isLoading: isEditing }] = useEditTeamRegistryMutation();

  const suggestions = useMemo(() => {
    const selectedIds = new Set(admins.map((user) => user.id));
    return (candidateAdmins ?? []).filter((user) => !selectedIds.has(user.id));
  }, [candidateAdmins, admins]);

  const trimmedName = name.trim();
  const trimmedDescription = description.trim();
  // Left empty on a team that still has the default description: it stays.
  const keepsPlaceholder = !!team?.description_is_placeholder && trimmedDescription === "";
  const descriptionValid = isValidTeamDescription(description) || keepsPlaceholder;
  // `maxLength` stops typing silently: say why once the limit is reached.
  const descriptionAtLimit = description.length >= TEAM_DESCRIPTION_MAX_LENGTH;

  const changes = useMemo((): EditTeamRegistryRequest => {
    if (!team) return {};
    const initialIds = new Set(initialAdmins.map((user) => user.id));
    const currentIds = new Set(admins.map((user) => user.id));
    const request: EditTeamRegistryRequest = {};
    if (trimmedName !== team.name) request.name = trimmedName;
    if (!keepsPlaceholder && trimmedDescription !== storedDescription) request.description = trimmedDescription;
    const added = admins.filter((user) => !initialIds.has(user.id)).map((user) => user.id);
    const removed = initialAdmins.filter((user) => !currentIds.has(user.id)).map((user) => user.id);
    if (added.length > 0) request.add_admin_ids = added;
    if (removed.length > 0) request.remove_admin_ids = removed;
    return request;
  }, [team, initialAdmins, admins, trimmedName, trimmedDescription, storedDescription, keepsPlaceholder]);

  const canSubmit =
    trimmedName.length > 0 &&
    descriptionValid &&
    admins.length > 0 &&
    !isCreating &&
    !isEditing &&
    (!team || Object.keys(changes).length > 0);

  const handleConfirm = async () => {
    if (!canSubmit) return;
    await runMutationAction({
      action: () =>
        team
          ? editTeam({ teamId: team.id, editTeamRegistryRequest: changes }).unwrap()
          : createTeam({
              createTeamRequest: {
                name: trimmedName,
                description: trimmedDescription,
                initial_team_admin_ids: admins.map((user) => user.id),
              },
            }).unwrap(),
      onSuccess: () => {
        showSuccess({ summary: t(`${keys}.successSummary`) });
        onClose();
      },
      onError: (error) => {
        const refusalKey = REFUSAL_KEYS[normalizeApiError(error).code ?? ""];
        if (refusalKey) {
          showError({ summary: t(`${keys}.errors.summary`), detail: t(refusalKey) });
          return;
        }
        notifyApiError(error, {
          summary: t(`${keys}.errors.summary`),
          fallbackDetail: t(`${keys}.errors.fallbackDetail`),
          forbiddenDetail: t(`${keys}.errors.forbiddenDetail`),
          conflictDetail: t(`${keys}.errors.conflictDetail`),
        });
      },
    });
  };

  return (
    <Dialog
      open
      title={t(`${keys}.title`)}
      confirmLabel={t(`${keys}.submit`)}
      confirmDisabled={!canSubmit}
      onConfirm={() => void handleConfirm()}
      onCancel={onClose}
      maxWidth={560}
    >
      <div className={styles.teamForm}>
        <TextInput
          label={t("rework.adminTeams.createTeam.nameLabel")}
          placeholder={t("rework.adminTeams.createTeam.namePlaceholder")}
          value={name}
          maxLength={MAX_TEAM_NAME_LENGTH}
          onChange={(event) => setName(event.target.value)}
          required
        />
        <TextArea
          label={t("rework.teamDescription.label")}
          description={t("rework.teamDescription.helper")}
          error={
            descriptionTouched && !descriptionValid
              ? t("rework.teamDescription.tooShort", { min: TEAM_DESCRIPTION_MIN_LENGTH })
              : undefined
          }
          explanation={
            descriptionAtLimit
              ? t("rework.teamDescription.maxReached", { max: TEAM_DESCRIPTION_MAX_LENGTH })
              : undefined
          }
          maxLength={TEAM_DESCRIPTION_MAX_LENGTH}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          onBlur={() => setDescriptionTouched(true)}
          required
        />
        <div className={styles.adminsField}>
          <span className={styles.adminsLabel}>{t("rework.adminTeams.createTeam.adminsLabel")} *</span>
          <div className={styles.adminsPicker}>
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
              onSelect={(user) => {
                setAdmins((previous) => [...previous, user]);
                setAdminQuery("");
              }}
            />
            {admins.length > 0 && (
              <ul className={styles.adminChipList}>
                {admins.map((user) => {
                  const name = `${user.first_name} ${user.last_name}`;
                  const pending = pendingAdminIds.has(user.id);
                  return (
                    <li key={user.id}>
                      <Chip
                        label={name}
                        secondary={pending ? t("rework.adminTeams.pendingAdmin") : undefined}
                        title={pending ? t("rework.adminTeams.pendingAdminHint", { name }) : undefined}
                        onRemove={() => setAdmins((previous) => previous.filter((u) => u.id !== user.id))}
                      />
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </Dialog>
  );
}
