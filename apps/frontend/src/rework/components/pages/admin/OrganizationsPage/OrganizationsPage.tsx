// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Separator from "@shared/atoms/Separator/Separator";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useOrganizationRegistryQuery,
  useCreateOrganizationMutation,
} from "../../../../../slices/fredManager/fredManagerApiEnhancements";
import styles from "../AdminTeamsPage/AdminTeamsPage.module.css";

export default function OrganizationsPage() {
  const { t } = useTranslation();
  const access = useManagerPlatformAdmin();
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const after = cursors[cursors.length - 1];
  const registry = useOrganizationRegistryQuery({ after }, { skip: !access.isAdmin, refetchOnMountOrArgChange: true });
  const [createOrganization, result] = useCreateOrganizationMutation();
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("");
  const [admin, setAdmin] = useState("");
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
  const canSubmit = access.isAdmin && !busy && name.trim() !== "" && owner.trim() !== "" && admin.trim() !== "";
  const error = result.error ? normalizeApiError(result.error) : null;
  const page = !registry.isError && !registry.isFetching ? registry.currentData : undefined;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit || submitting.current) return;
    submitting.current = true;
    setCreatedName("");
    try {
      const organization = await createOrganization({
        createOrganization: {
          name: name.trim(),
          owner_username: owner.trim(),
          admin_username: admin.trim(),
        },
      }).unwrap();
      if (!active.current) return;
      setCreatedName(organization.name);
      setName("");
      setOwner("");
      setAdmin("");
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
            <TextInput
              label={t("rework.organizations.owner")}
              value={owner}
              onChange={(event) => setOwner(event.target.value)}
              disabled={busy}
              required
              maxLength={255}
            />
            <TextInput
              label={t("rework.organizations.admin")}
              value={admin}
              onChange={(event) => setAdmin(event.target.value)}
              disabled={busy}
              required
              maxLength={255}
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
