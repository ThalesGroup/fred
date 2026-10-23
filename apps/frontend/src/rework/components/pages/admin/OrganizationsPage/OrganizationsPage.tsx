// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete";
import Chip from "@shared/atoms/Chip/Chip";
import type { UserSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import Separator from "@shared/atoms/Separator/Separator";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useOrganizationRegistryQuery,
  useSearchOrganizationCandidatesQuery,
  useCreateOrganizationMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "../AdminTeamsPage/AdminTeamsPage.module.css";

// Reuse Swift's candidate search and selection controls independently for each role.
function OrganizationContact({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: UserSummary | null;
  onChange: (user: UserSummary | null) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const trimmedQuery = query.trim();
  const { currentData, isFetching, isError } = useSearchOrganizationCandidatesQuery(
    { query: trimmedQuery },
    { skip: disabled || !!value || trimmedQuery.length < 2 },
  );
  return (
    <div>
      <Autocomplete
        textInput={{ label, value: query, disabled: disabled || !!value }}
        minQueryLength={2}
        onFieldValueChange={setQuery}
        noOptionsMessage={t(
          isFetching
            ? "rework.adminTeams.createTeam.adminsSearching"
            : isError
              ? "rework.organizations.searchFailed"
              : "rework.adminTeams.createTeam.adminsNoMatch",
        )}
        options={(!disabled && !value && trimmedQuery.length >= 2 && !isError ? (currentData ?? []) : [])
          .filter((user) => !!user.username)
          .map((user) => ({
            label: `${user.first_name ?? ""} ${user.last_name ?? ""} (${user.username})`,
            value: user,
            key: user.id,
          }))}
        onSelect={(user) => {
          onChange(user);
          setQuery("");
        }}
      />
      {value && (
        <Chip
          label={`${value.first_name ?? ""} ${value.last_name ?? ""} (${value.username})`}
          removeAriaLabel={t("rework.adminTeams.createTeam.adminRemove", { name: value.username })}
          onRemove={disabled ? undefined : () => onChange(null)}
        />
      )}
    </div>
  );
}

export default function OrganizationsPage() {
  const { t } = useTranslation();
  const access = useManagerPlatformAdmin();
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const after = cursors[cursors.length - 1];
  const registry = useOrganizationRegistryQuery({ after }, { skip: !access.isAdmin, refetchOnMountOrArgChange: true });
  const [createOrganization, result] = useCreateOrganizationMutation();
  const [name, setName] = useState("");
  const [owner, setOwner] = useState<UserSummary | null>(null);
  const [admin, setAdmin] = useState<UserSummary | null>(null);
  const [createdName, setCreatedName] = useState("");
  const submitting = useRef(false);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const busy = result.isLoading || access.isFetching;
  const canSubmit = access.isAdmin && !busy && name.trim() !== "" && !!owner?.username && !!admin?.username;
  const error = result.error ? normalizeApiError(result.error) : null;
  const page = !registry.isError && !registry.isFetching ? registry.currentData : undefined;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit || submitting.current || !owner?.username || !admin?.username) return;
    submitting.current = true;
    setCreatedName("");
    try {
      const organization = await createOrganization({
        createOrganization: {
          name: name.trim(),
          owner_username: owner.username,
          admin_username: admin.username,
        },
      }).unwrap();
      if (!active.current) return;
      setCreatedName(organization.name);
      setName("");
      setOwner(null);
      setAdmin(null);
      setCursors([undefined]);
      if (!after) void registry.refetch();
    } catch {
      // RTK exposes the error. Creation is never replayed automatically.
    } finally {
      submitting.current = false;
    }
  };

  return (
    <div className={styles.adminTeamsPage}>
      <PageHeader title={t("rework.organizations.title")} />
      {access.isLoading || access.isFetching ? (
        <p role="status">{t("common.loading")}</p>
      ) : access.isError ? (
        <div role="alert">
          <p>{t("rework.provisioning.authorityUnavailable")}</p>
          <Button color="primary" variant="outlined" size="medium" onClick={() => void access.refetch()}>
            {t("rework.provisioning.retryAuthority")}
          </Button>
        </div>
      ) : !access.isAdmin ? (
        <p role="alert">{t("rework.provisioning.forbidden")}</p>
      ) : (
        <>
          <section className={styles.existingTeamsSection}>
            <h2 className={styles.sectionTitle}>{t("rework.organizations.existing")}</h2>
            {registry.isError ? (
              <div role="alert">
                <p>{t("rework.organizations.loadFailed")}</p>
                <Button color="primary" variant="outlined" size="medium" onClick={() => void registry.refetch()}>
                  {t("rework.provisioning.retryAuthority")}
                </Button>
              </div>
            ) : !page ? (
              <p role="status">{t("common.loading")}</p>
            ) : page.items.length === 0 ? (
              <p className={styles.emptyTeamsMessage}>{t("rework.organizations.empty")}</p>
            ) : (
              <DataTable
                data={page.items}
                columns={[
                  {
                    label: t("rework.adminTeams.existingTeams.table.name"),
                    cellRenderer: (organization) => <span>{organization.name}</span>,
                  },
                ]}
              />
            )}
            <div className={styles.actions}>
              <Button
                color="on-surface"
                variant="outlined"
                size="small"
                disabled={cursors.length < 2 || registry.isFetching}
                onClick={() => setCursors((previous) => previous.slice(0, -1))}
              >
                {t("dataTable.pagination.prev")}
              </Button>
              <Button
                color="on-surface"
                variant="outlined"
                size="small"
                disabled={!page?.next_cursor}
                onClick={() => {
                  if (page?.next_cursor) setCursors((previous) => [...previous, page.next_cursor!]);
                }}
              >
                {t("dataTable.pagination.next")}
              </Button>
            </div>
          </section>
          <Separator />
          <form onSubmit={submit} className={styles.createTeamSection} aria-busy={result.isLoading}>
            <h2 className={styles.sectionTitle}>{t("rework.organizations.create")}</h2>
            <p className={styles.sectionDescription}>{t("rework.organizations.accountsHint")}</p>
            <TextInput
              label={t("rework.organizations.name")}
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={busy}
              required
              maxLength={180}
            />
            <OrganizationContact
              label={t("rework.organizations.owner")}
              value={owner}
              onChange={setOwner}
              disabled={busy}
            />
            <OrganizationContact
              label={t("rework.organizations.admin")}
              value={admin}
              onChange={setAdmin}
              disabled={busy}
            />
            <div className={styles.actions}>
              <Button type="submit" color="primary" variant="filled" size="medium" disabled={!canSubmit}>
                {t("rework.organizations.create")}
              </Button>
            </div>
            {error && (
              <div role="alert">
                <p>{t("rework.organizations.createFailed")}</p>
                <p>{error.status ? error.detail : t("rework.provisioning.networkError")}</p>
              </div>
            )}
            {createdName && <p role="status">{t("rework.organizations.created", { name: createdName })}</p>}
          </form>
        </>
      )}
    </div>
  );
}
