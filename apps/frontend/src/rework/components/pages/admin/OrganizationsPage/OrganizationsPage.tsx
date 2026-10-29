// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { useOrganizationRegistryQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Space } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import OrganizationFormDialog from "./OrganizationFormDialog";
import styles from "../AdminTeamsPage/AdminTeamsPage.module.css";

export default function OrganizationsPage() {
  const { t } = useTranslation();
  const access = useManagerPlatformAdmin();
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const after = cursors[cursors.length - 1];
  const registry = useOrganizationRegistryQuery({ after }, { skip: !access.isAdmin, refetchOnMountOrArgChange: true });
  // `null`: closed; `"create"`: a new organization; an organization: its edit.
  const [form, setForm] = useState<Space | "create" | null>(null);
  const page = !registry.isError && !registry.isFetching ? registry.currentData : undefined;

  // A new organization can land on any page: go back to the first one. An edit patches
  // the cached rows itself.
  const handleSaved = () => {
    if (form !== "create") return;
    setCursors([undefined]);
    if (!after) void registry.refetch();
  };

  return (
    <div className={styles.adminTeamsPage}>
      <PageHeader
        title={t("rework.organizations.title")}
        actions={
          access.isAdmin && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setForm("create")}
            >
              {t("rework.organizations.createOrganization.open")}
            </Button>
          )
        }
      />
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
                  label: t("rework.organizations.name"),
                  cellRenderer: (organization) => <span>{organization.name}</span>,
                },
                {
                  label: "",
                  // Cell padding plus the 40px medium button: narrower squeezes it into an oval.
                  size: "4rem",
                  cellRenderer: (organization) => (
                    <IconButton
                      variant="icon"
                      size="medium"
                      color="on-surface-retreat"
                      icon={{ category: "outlined", type: "edit" }}
                      aria-label={t("rework.organizations.editOrganization.openAria", { name: organization.name })}
                      onClick={() => setForm(organization)}
                    />
                  ),
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
      )}
      {form && (
        <OrganizationFormDialog
          organization={form === "create" ? undefined : form}
          onSaved={handleSaved}
          onClose={() => setForm(null)}
        />
      )}
    </div>
  );
}
