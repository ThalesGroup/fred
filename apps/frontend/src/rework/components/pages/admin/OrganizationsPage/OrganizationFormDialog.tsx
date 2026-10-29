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

// Mirrors the server's bound on administrators per organization.
const MAX_ORGANIZATION_ADMINS = 50;

// Chosen accounts as chips; the search field stays until `max` accounts are chosen.
function AccountPicker({
  label,
  value,
  onChange,
  max = 1,
}: {
  label: string;
  value: UserSummary[];
  onChange: (users: UserSummary[]) => void;
  max?: number;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const trimmedQuery = query.trim();
  const full = value.length >= max;
  // `currentData`, not `data`: results of a previous search must not stay selectable while a new one loads.
  const { currentData, isFetching, isError } = useSearchOrganizationCandidatesQuery(
    { query: trimmedQuery },
    { skip: full || trimmedQuery.length < 2 },
  );
  return (
    <div className={styles.adminsField}>
      <span className={styles.adminsLabel}>{label} *</span>
      <div className={styles.adminsPicker}>
        {!full && (
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
              .filter((user) => !!user.username && !value.some((chosen) => chosen.id === user.id))
              .map((user) => ({ label: userLabel(user), value: user, key: user.id }))}
            onSelect={(user) => {
              onChange([...value, user]);
              setQuery("");
            }}
          />
        )}
        {value.length > 0 && (
          <ul className={styles.adminChipList}>
            {value.map((user) => (
              <li key={user.id}>
                <Chip
                  label={userLabel(user)}
                  removeAriaLabel={t("rework.adminTeams.createTeam.adminRemove", { name: user.username ?? user.id })}
                  onRemove={() => onChange(value.filter((other) => other.id !== user.id))}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
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

// Saving a new owner replaces every current one: say so when there are several.
function SeveralOwners({ owners }: { owners?: UserSummary[] }) {
  const { t } = useTranslation();
  if (!owners || owners.length < 2) return null;
  return (
    <p role="note" className={styles.sectionDescription}>
      {t("rework.organizations.editOrganization.severalOwners", { names: owners.map(userLabel).join(", ") })}
    </p>
  );
}

const sameAccounts = (a: UserSummary[], b: UserSummary[]) =>
  a.length === b.length && a.every((user) => b.some((other) => other.id === user.id));

interface OrganizationFormDialogProps {
  /** The organization to edit; absent to create one. */
  organization?: Space;
  onSaved: (organization: Space) => void;
  onClose: () => void;
}

/** Create or edit an organization's name, owner and administrators. An edit sends only what changed. */
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
  const [owner, setOwner] = useState<UserSummary | null>(null);
  const [admins, setAdmins] = useState<UserSummary[]>([]);
  // Pre-fill once, from this open's own fetch rather than a cached copy; a later refetch
  // must not overwrite what the admin typed.
  const fresh = !detailQuery.isFetching && detailQuery.requestId !== cachedRequestId;
  if (detailQuery.currentData && fresh && !detail) {
    setDetail(detailQuery.currentData);
    setName(detailQuery.currentData.organization.name);
    setOwner(detailQuery.currentData.owners[0] ?? null);
    setAdmins(detailQuery.currentData.admins);
  }
  const ready = !organization || !!detail;

  const trimmedName = name.trim();
  // Owners can have several direct holders: saving makes the chosen account the only one.
  // Administrators are sent as the complete list, only when it changed.
  const adminsChanged = !detail || !sameAccounts(admins, detail.admins);
  // A holder the directory no longer names cannot be sent back in a changed list.
  const unnamedAdminBlocks = adminsChanged && admins.some((user) => !user.username);
  const changes: UpdateOrganization = {};
  if (detail) {
    if (trimmedName !== detail.organization.name) changes.name = trimmedName;
    if (owner?.username && owner.id !== detail.owners[0]?.id) changes.owner_username = owner.username;
    if (adminsChanged) changes.admin_usernames = admins.map((user) => user.username!);
  }
  // An untouched holder is kept as is, even one the directory no longer names.
  const kept = (user: UserSummary | null, current?: UserSummary) =>
    !!user && (!!user.username || (!!current && user.id === current.id));
  const canSubmit =
    ready &&
    trimmedName !== "" &&
    kept(owner, detail?.owners[0]) &&
    admins.length > 0 &&
    !unnamedAdminBlocks &&
    !isCreating &&
    !isUpdating &&
    (!organization || Object.keys(changes).length > 0);

  const handleConfirm = async () => {
    if (!canSubmit || !owner) return;
    await runMutationAction({
      action: async () =>
        organization
          ? (await updateOrganization({ id: organization.id, updateOrganization: changes }).unwrap()).organization
          : createOrganization({
              createOrganization: {
                name: trimmedName,
                owner_username: owner.username!,
                admin_usernames: admins.map((user) => user.username!),
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
          <AccountPicker
            label={t("rework.organizations.owner")}
            value={owner ? [owner] : []}
            onChange={(users) => setOwner(users[0] ?? null)}
          />
          <SeveralOwners owners={detail?.owners} />
          <AccountPicker
            label={t("rework.organizations.admin")}
            value={admins}
            onChange={setAdmins}
            max={MAX_ORGANIZATION_ADMINS}
          />
          {unnamedAdminBlocks && (
            <p role="note" className={styles.sectionDescription}>
              {t("rework.organizations.editOrganization.unnamedAdmins")}
            </p>
          )}
        </div>
      )}
    </Dialog>
  );
}
