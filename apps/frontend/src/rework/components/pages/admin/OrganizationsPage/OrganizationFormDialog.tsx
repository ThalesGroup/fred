// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete";
import Chip from "@shared/atoms/Chip/Chip";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast";
import { useMutationAction } from "@core/hooks/useMutationAction";
import {
  useCreateOrganizationMutation,
  useSearchOrganizationCandidatesQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Space, UserSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "../AdminTeamsPage/AdminTeamsPage.module.css";

const MAX_ORGANIZATION_NAME_LENGTH = 180;
const keys = "rework.organizations.createOrganization";

const userLabel = (user: UserSummary) => `${user.first_name ?? ""} ${user.last_name ?? ""} (${user.username})`;

// One account per role: the search field gives way to the chosen person's chip.
function AccountPicker({
  label,
  value,
  onChange,
}: {
  label: string;
  value: UserSummary | null;
  onChange: (user: UserSummary | null) => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const trimmedQuery = query.trim();
  // `currentData`, not `data`: results of a previous search must not stay selectable while a new one loads.
  const { currentData, isFetching, isError } = useSearchOrganizationCandidatesQuery(
    { query: trimmedQuery },
    { skip: !!value || trimmedQuery.length < 2 },
  );
  return (
    <div className={styles.adminsField}>
      <span className={styles.adminsLabel}>{label} *</span>
      {value ? (
        <ul className={styles.adminChipList}>
          <li>
            <Chip
              label={userLabel(value)}
              removeAriaLabel={t("rework.adminTeams.createTeam.adminRemove", { name: value.username })}
              onRemove={() => onChange(null)}
            />
          </li>
        </ul>
      ) : (
        <Autocomplete<UserSummary>
          textInput={{
            placeholder: t("rework.adminTeams.createTeam.adminsPlaceholder"),
            size: "small",
            icon: { category: "outlined", type: "search" },
            "aria-label": label,
          }}
          minQueryLength={2}
          onFieldValueChange={setQuery}
          noOptionsMessage={t(
            isFetching
              ? "rework.adminTeams.createTeam.adminsSearching"
              : isError
                ? "rework.organizations.searchFailed"
                : "rework.adminTeams.createTeam.adminsNoMatch",
          )}
          options={(trimmedQuery.length >= 2 && !isError ? (currentData ?? []) : [])
            .filter((user) => !!user.username)
            .map((user) => ({ label: userLabel(user), value: user, key: user.id }))}
          onSelect={(user) => {
            onChange(user);
            setQuery("");
          }}
        />
      )}
    </div>
  );
}

interface OrganizationFormDialogProps {
  onCreated: (organization: Space) => void;
  onClose: () => void;
}

/** Create an organization with its owner and administrator. Create only: there is no edit endpoint yet. */
export default function OrganizationFormDialog({ onCreated, onClose }: OrganizationFormDialogProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const [createOrganization, { isLoading }] = useCreateOrganizationMutation();
  const [name, setName] = useState("");
  const [owner, setOwner] = useState<UserSummary | null>(null);
  const [admin, setAdmin] = useState<UserSummary | null>(null);

  const trimmedName = name.trim();
  const canSubmit = trimmedName !== "" && !!owner?.username && !!admin?.username && !isLoading;

  const handleConfirm = async () => {
    if (!canSubmit || !owner?.username || !admin?.username) return;
    await runMutationAction({
      action: () =>
        createOrganization({
          createOrganization: { name: trimmedName, owner_username: owner.username!, admin_username: admin.username! },
        }).unwrap(),
      onSuccess: (organization) => {
        showSuccess({ summary: t(`${keys}.successSummary`, { name: organization.name }) });
        onCreated(organization);
        onClose();
      },
      onError: (error) =>
        notifyApiError(error, {
          summary: t(`${keys}.errors.summary`),
          fallbackDetail: t(`${keys}.errors.fallbackDetail`),
          forbiddenDetail: t(`${keys}.errors.forbiddenDetail`),
          conflictDetail: t(`${keys}.errors.conflictDetail`),
          validationDetail: t(`${keys}.errors.validationDetail`),
        }),
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
      dense
      dismissible={false}
    >
      <div className={styles.teamForm}>
        <p className={styles.sectionDescription}>{t("rework.organizations.accountsHint")}</p>
        <TextInput
          label={t("rework.organizations.name")}
          placeholder={t(`${keys}.namePlaceholder`)}
          size="small"
          value={name}
          maxLength={MAX_ORGANIZATION_NAME_LENGTH}
          onChange={(event) => setName(event.target.value)}
          required
        />
        <AccountPicker label={t("rework.organizations.owner")} value={owner} onChange={setOwner} />
        <AccountPicker label={t("rework.organizations.admin")} value={admin} onChange={setAdmin} />
      </div>
    </Dialog>
  );
}
