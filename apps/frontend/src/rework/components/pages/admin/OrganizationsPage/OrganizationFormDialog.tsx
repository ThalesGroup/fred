// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete";
import Chip from "@shared/atoms/Chip/Chip";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
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

// The directory may not describe a holder any more: its id stands in for the username.
const userLabel = (user: UserSummary) => {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
  const handle = user.username ?? user.id;
  return name ? `${name} (${handle})` : handle;
};

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
              removeAriaLabel={t("rework.adminTeams.createTeam.adminRemove", { name: value.username ?? value.id })}
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

// Server details are English and generic: every refusal gets our own wording.
function refusalKey(error: unknown, editing: boolean): string | undefined {
  const { status, code } = normalizeApiError(error);
  const keys = `rework.organizations.${editing ? "edit" : "create"}Organization.errors`;
  if (status === 403) return `${keys}.forbiddenDetail`;
  if (status === 400 || status === 422) return `${keys}.validationDetail`;
  if (status === 404 && editing) return `${keys}.notFoundDetail`;
  if (status === 409)
    return editing && code === "space_pending_deletion" ? `${keys}.retiredDetail` : `${keys}.conflictDetail`;
  return undefined;
}

// Saving a new holder replaces every current one: say so when there are several.
function SeveralHolders({ holders, messageKey }: { holders?: UserSummary[]; messageKey: string }) {
  const { t } = useTranslation();
  if (!holders || holders.length < 2) return null;
  return (
    <p role="note" className={styles.sectionDescription}>
      {t(messageKey, { names: holders.map(userLabel).join(", ") })}
    </p>
  );
}

interface OrganizationFormDialogProps {
  /** The organization to edit; absent to create one. */
  organization?: Space;
  onSaved: (organization: Space) => void;
  onClose: () => void;
}

/** Create or edit an organization's name, technical admin and business owner. An edit sends only what changed. */
export default function OrganizationFormDialog({ organization, onSaved, onClose }: OrganizationFormDialogProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { runMutationAction } = useMutationAction();
  const [createOrganization, { isLoading: isCreating }] = useCreateOrganizationMutation();
  const [updateOrganization, { isLoading: isUpdating }] = useUpdateOrganizationMutation();
  const keys = `rework.organizations.${organization ? "edit" : "create"}Organization`;
  // Fetched on every open: the roles are not part of the registry page.
  const detailQuery = useGetOrganizationQuery(
    { id: organization?.id ?? "" },
    { skip: !organization, refetchOnMountOrArgChange: true },
  );
  // On a warm cache the first render already has a detail, from an earlier request.
  const [cachedRequestId] = useState(detailQuery.requestId);
  const [detail, setDetail] = useState<OrganizationDetail>();
  const [name, setName] = useState("");
  const [admin, setAdmin] = useState<UserSummary | null>(null);
  const [owner, setOwner] = useState<UserSummary | null>(null);
  // Pre-fill once, from this open's own fetch rather than a cached copy; a later refetch
  // must not overwrite what the platform admin typed.
  const fresh = !detailQuery.isFetching && detailQuery.requestId !== cachedRequestId;
  if (detailQuery.currentData && fresh && !detail) {
    setDetail(detailQuery.currentData);
    setName(detailQuery.currentData.organization.name);
    setAdmin(detailQuery.currentData.admins[0] ?? null);
    setOwner(detailQuery.currentData.owners[0] ?? null);
  }
  const ready = !organization || !!detail;

  const trimmedName = name.trim();
  // A role can have several direct holders: saving makes the chosen account the only one.
  const changes: UpdateOrganization = {};
  if (detail) {
    if (trimmedName !== detail.organization.name) changes.name = trimmedName;
    if (admin?.username && admin.id !== detail.admins[0]?.id) changes.admin_username = admin.username;
    if (owner?.username && owner.id !== detail.owners[0]?.id) changes.owner_username = owner.username;
  }
  // An untouched holder is kept as is, even one the directory no longer names.
  const kept = (user: UserSummary | null, current?: UserSummary) =>
    !!user && (!!user.username || (!!current && user.id === current.id));
  const canSubmit =
    ready &&
    trimmedName !== "" &&
    kept(admin, detail?.admins[0]) &&
    kept(owner, detail?.owners[0]) &&
    !isCreating &&
    !isUpdating &&
    (!organization || Object.keys(changes).length > 0);

  const handleConfirm = async () => {
    if (!canSubmit || !admin || !owner) return;
    await runMutationAction({
      action: async () =>
        organization
          ? (await updateOrganization({ id: organization.id, updateOrganization: changes }).unwrap()).organization
          : createOrganization({
              createOrganization: {
                name: trimmedName,
                admin_username: admin.username!,
                owner_username: owner.username!,
              },
            }).unwrap(),
      onSuccess: (saved) => {
        showSuccess({ summary: t(`${keys}.successSummary`, { name: saved.name }) });
        onSaved(saved);
        onClose();
      },
      onError: (error) =>
        showError({
          summary: t(`${keys}.errors.summary`),
          detail: t(refusalKey(error, !!organization) ?? `${keys}.errors.fallbackDetail`),
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
      {!ready ? (
        detailQuery.isError ? (
          <p role="alert">
            {t(refusalKey(detailQuery.error, true) ?? "rework.organizations.editOrganization.loadFailed")}
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
          <AccountPicker label={t("rework.organizations.admin")} value={admin} onChange={setAdmin} />
          <SeveralHolders holders={detail?.admins} messageKey="rework.organizations.editOrganization.severalAdmins" />
          <AccountPicker label={t("rework.organizations.owner")} value={owner} onChange={setOwner} />
          <SeveralHolders holders={detail?.owners} messageKey="rework.organizations.editOrganization.severalOwners" />
        </div>
      )}
    </Dialog>
  );
}
