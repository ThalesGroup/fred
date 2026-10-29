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
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useCreateOrganizationMutation,
  useGetOrganizationQuery,
  useSearchOrganizationCandidatesQuery,
  useUpdateOrganizationMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  OrganizationDetail,
  Space,
  UpdateOrganization,
  UserSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "../AdminTeamsPage/AdminTeamsPage.module.css";

const MAX_ORGANIZATION_NAME_LENGTH = 180;

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

// The server's 409 and 404 details are English and generic: show our own wording.
function editRefusalKey(error: unknown): string | undefined {
  const { status, code } = normalizeApiError(error);
  if (status === 404) return "rework.organizations.editOrganization.errors.notFoundDetail";
  if (status === 409) {
    return code === "space_pending_deletion"
      ? "rework.organizations.editOrganization.errors.retiredDetail"
      : "rework.organizations.editOrganization.errors.conflictDetail";
  }
  return undefined;
}

interface OrganizationFormDialogProps {
  /** The organization to edit; absent to create one. */
  organization?: Space;
  onSaved: (organization: Space) => void;
  onClose: () => void;
}

/** Create or edit an organization's name, owner and administrator. An edit sends only what changed. */
export default function OrganizationFormDialog({ organization, onSaved, onClose }: OrganizationFormDialogProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const [createOrganization, { isLoading: isCreating }] = useCreateOrganizationMutation();
  const [updateOrganization, { isLoading: isUpdating }] = useUpdateOrganizationMutation();
  const keys = `rework.organizations.${organization ? "edit" : "create"}Organization`;
  // Fetched on every open: the roles are not part of the registry page.
  const detailQuery = useGetOrganizationQuery(
    { id: organization?.id ?? "" },
    { skip: !organization, refetchOnMountOrArgChange: true },
  );
  const [detail, setDetail] = useState<OrganizationDetail>();
  const [name, setName] = useState("");
  const [owner, setOwner] = useState<UserSummary | null>(null);
  const [admin, setAdmin] = useState<UserSummary | null>(null);
  // Pre-fill once; a later refetch must not overwrite what the admin typed.
  if (detailQuery.currentData && !detail) {
    setDetail(detailQuery.currentData);
    setName(detailQuery.currentData.organization.name);
    setOwner(detailQuery.currentData.owners[0] ?? null);
    setAdmin(detailQuery.currentData.admins[0] ?? null);
  }
  const ready = !organization || !!detail;

  const trimmedName = name.trim();
  // A role can have several direct holders: saving makes the chosen account the only one.
  const changes: UpdateOrganization = {};
  if (detail) {
    if (trimmedName !== detail.organization.name) changes.name = trimmedName;
    if (owner?.username && owner.username !== detail.owners[0]?.username) changes.owner_username = owner.username;
    if (admin?.username && admin.username !== detail.admins[0]?.username) changes.admin_username = admin.username;
  }
  const canSubmit =
    ready &&
    trimmedName !== "" &&
    !!owner?.username &&
    !!admin?.username &&
    !isCreating &&
    !isUpdating &&
    (!organization || Object.keys(changes).length > 0);

  const handleConfirm = async () => {
    if (!canSubmit || !owner?.username || !admin?.username) return;
    await runMutationAction({
      action: async () =>
        organization
          ? (await updateOrganization({ id: organization.id, updateOrganization: changes }).unwrap()).organization
          : createOrganization({
              createOrganization: {
                name: trimmedName,
                owner_username: owner.username!,
                admin_username: admin.username!,
              },
            }).unwrap(),
      onSuccess: (saved) => {
        showSuccess({ summary: t(`${keys}.successSummary`, { name: saved.name }) });
        onSaved(saved);
        onClose();
      },
      onError: (error) => {
        const refusalKey = organization ? editRefusalKey(error) : undefined;
        if (refusalKey) {
          showError({ summary: t(`${keys}.errors.summary`), detail: t(refusalKey) });
          return;
        }
        notifyApiError(error, {
          summary: t(`${keys}.errors.summary`),
          fallbackDetail: t(`${keys}.errors.fallbackDetail`),
          forbiddenDetail: t(`${keys}.errors.forbiddenDetail`),
          conflictDetail: t(`${keys}.errors.conflictDetail`),
          validationDetail: t(`${keys}.errors.validationDetail`),
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
      dense
      dismissible={false}
    >
      {!ready ? (
        detailQuery.isError ? (
          <p role="alert">
            {t(editRefusalKey(detailQuery.error) ?? "rework.organizations.editOrganization.loadFailed")}
          </p>
        ) : (
          <p role="status">{t("common.loading")}</p>
        )
      ) : (
        <div className={styles.teamForm}>
          <p className={styles.sectionDescription}>{t("rework.organizations.accountsHint")}</p>
          <TextInput
            label={t("rework.organizations.name")}
            placeholder={t("rework.organizations.createOrganization.namePlaceholder")}
            size="small"
            value={name}
            maxLength={MAX_ORGANIZATION_NAME_LENGTH}
            onChange={(event) => setName(event.target.value)}
            // The edit form replaces the loading state inside the open dialog: bring focus to it.
            autoFocus={!!organization}
            required
          />
          <AccountPicker label={t("rework.organizations.owner")} value={owner} onChange={setOwner} />
          <AccountPicker label={t("rework.organizations.admin")} value={admin} onChange={setAdmin} />
        </div>
      )}
    </Dialog>
  );
}
