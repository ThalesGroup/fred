// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Switch from "@shared/atoms/Switch/Switch";
import Select from "@shared/molecules/Select/Select";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  usePlatformApplicationsQuery,
  useCreateApplicationMutation,
  useUpdateApplicationMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  Application,
  CreateApplication,
  SpacePermission,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "../AdminTeamsPage/AdminTeamsPage.module.css";

const prefix = "rework.applications";
// These are the existing space permissions accepted by application registration.
const permissions: SpacePermission[] = [
  "read",
  "write",
  "manage",
  "run_evaluations",
  "manage_evaluation_corpus",
  "read_conversations_for_evaluation",
  "read_usage",
];

export default function PlatformApplicationsPage() {
  const { t } = useTranslation();
  const access = useManagerPlatformAdmin();
  const registry = usePlatformApplicationsQuery(undefined, { skip: !access.isAdmin, refetchOnMountOrArgChange: true });
  const [form, setForm] = useState<Application | "create" | null>(null);
  return (
    <div className={styles.adminTeamsPage}>
      <PageHeader
        title={t("teamAppsPage.title")}
        subtitle={t(`${prefix}.registryHint`)}
        actions={
          access.isAdmin && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setForm("create")}
            >
              {t(`${prefix}.create`)}
            </Button>
          )
        }
      />
      {access.isLoading || (access.isFetching && !access.currentData) ? (
        <p role="status">{t("common.loading")}</p>
      ) : access.isError ? (
        <p role="alert">{t("rework.provisioning.authorityUnavailable")}</p>
      ) : !access.isAdmin ? (
        <p role="alert">{t("rework.provisioning.forbidden")}</p>
      ) : registry.isError ? (
        <p role="alert">{t("teamAppsPage.loadError")}</p>
      ) : !registry.currentData ? (
        <p role="status">{t("common.loading")}</p>
      ) : !registry.currentData.length ? (
        <p>{t("rework.admin.capabilities.emptyApps")}</p>
      ) : (
        <DataTable
          data={registry.currentData}
          rowKey={(app) => app.id}
          columns={[
            { label: t(`${prefix}.display_name`), cellRenderer: (app) => app.display_name },
            { label: t(`${prefix}.logical_name`), cellRenderer: (app) => app.logical_name },
            {
              label: t(`${prefix}.entry_permission`),
              cellRenderer: (app) => t(`${prefix}.permissions.${app.entry_permission}`),
            },
            {
              label: t(`${prefix}.enabled`),
              cellRenderer: (app) => t(`${prefix}.${app.enabled ? "active" : "inactive"}`),
            },
            {
              label: t("common.edit"),
              size: "4rem",
              cellRenderer: (app) => (
                <IconButton
                  variant="icon"
                  size="medium"
                  icon={{ category: "outlined", type: "edit" }}
                  aria-label={t(`${prefix}.editNamed`, { name: app.display_name })}
                  onClick={() => setForm(app)}
                />
              ),
            },
          ]}
        />
      )}
      {form && access.isAdmin && (
        <ApplicationForm
          key={form === "create" ? "create" : form.id}
          application={form === "create" ? undefined : form}
          onClose={() => setForm(null)}
        />
      )}
    </div>
  );
}

function ApplicationForm({ application, onClose }: { application?: Application; onClose: () => void }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<CreateApplication>(() => ({
    logical_name: application?.logical_name ?? "",
    display_name: application?.display_name ?? "",
    description: application?.description ?? "",
    icon: application?.icon ?? "widgets",
    version: application?.version ?? "1.0.0",
    ui_base_url: application?.ui_base_url ?? "",
    api_base_url: application?.api_base_url ?? "",
    entry_permission: application?.entry_permission ?? "read",
    display_name_by_lang: application?.display_name_by_lang ?? {},
    description_by_lang: application?.description_by_lang ?? {},
  }));
  const [enabled, setEnabled] = useState(application?.enabled ?? false);
  const [error, setError] = useState<string>();
  const [create, creating] = useCreateApplicationMutation();
  const [update, updating] = useUpdateApplicationMutation();
  const saving = useRef(false);
  const busy = creating.isLoading || updating.isLoading;
  const valid = [draft.logical_name, draft.display_name, draft.icon, draft.version, draft.ui_base_url].every(
    (value) => !!value?.trim(),
  );
  const save = async () => {
    if (!valid || saving.current) return;
    saving.current = true;
    setError(undefined);
    try {
      const { logical_name, ...fields } = { ...draft, api_base_url: draft.api_base_url?.trim() || null };
      if (application)
        await update({
          applicationId: application.id,
          updateApplication: {
            ...fields,
            entry_permission: fields.entry_permission ?? "read",
            expected_revision: application.revision,
            enabled,
          },
        }).unwrap();
      else await create({ createApplication: { ...fields, logical_name } }).unwrap();
      onClose();
    } catch (failure) {
      const status = normalizeApiError(failure).status;
      setError(status === 409 ? "conflict" : status === 400 || status === 422 ? "invalid" : "saveFailed");
    } finally {
      saving.current = false;
    }
  };
  const fields = [
    "logical_name",
    "display_name",
    "description",
    "icon",
    "version",
    "ui_base_url",
    "api_base_url",
  ] as const;
  return (
    <Dialog
      open
      title={t(`${prefix}.${application ? "edit" : "create"}`)}
      confirmLabel={t("common.save")}
      confirmDisabled={!valid || busy || (!!application && error === "conflict")}
      onConfirm={() => void save()}
      onCancel={() => {
        if (!busy) onClose();
      }}
      dismissible={!busy}
      maxWidth={640}
      dense
    >
      <div className={styles.teamForm}>
        {error && <p role="alert">{t(`${prefix}.${error}`)}</p>}
        {!application && <p>{t(`${prefix}.createdDisabled`)}</p>}
        {fields.map((field) => (
          <TextInput
            key={field}
            label={t(`${prefix}.${field}`)}
            value={draft[field] ?? ""}
            size="small"
            disabled={busy || (field === "logical_name" && !!application)}
            required={field !== "description" && field !== "api_base_url"}
            explanation={field === "ui_base_url" || field === "api_base_url" ? t(`${prefix}.${field}Hint`) : undefined}
            onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
          />
        ))}
        <Select
          label={t(`${prefix}.entry_permission`)}
          size="small"
          value={draft.entry_permission ?? "read"}
          disabled={busy}
          options={permissions.map((permission) => ({
            value: permission,
            key: permission,
            label: t(`${prefix}.permissions.${permission}`),
          }))}
          onChange={(entry_permission) => setDraft({ ...draft, entry_permission })}
        />
        {(["en", "fr"] as const).map((locale) => (
          <fieldset key={locale} disabled={busy}>
            <legend>{t(`${prefix}.locale.${locale}`)}</legend>
            {(["display_name_by_lang", "description_by_lang"] as const).map((field) => (
              <TextInput
                key={field}
                size="small"
                label={t(`${prefix}.${field}`)}
                value={draft[field]?.[locale] ?? ""}
                onChange={(event) => setDraft({ ...draft, [field]: { ...draft[field], [locale]: event.target.value } })}
              />
            ))}
          </fieldset>
        ))}
        {application && (
          <label>
            <Switch
              checked={enabled}
              onChange={() => setEnabled(!enabled)}
              disabled={busy}
              aria-label={t(`${prefix}.enabled`)}
            />
            {t(`${prefix}.enabled`)}
          </label>
        )}
      </div>
    </Dialog>
  );
}
