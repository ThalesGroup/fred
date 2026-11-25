// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Switch from "@shared/atoms/Switch/Switch";
import Select from "@shared/molecules/Select/Select";
import SettingsModal from "@shared/organisms/SettingsModal/SettingsModal";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { materialIcons, toIconType } from "@shared/utils/Type";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useOrganizationApplicationsQuery,
  useCreateApplicationMutation,
  useUpdateApplicationMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  Application,
  CreateApplication,
  SpacePermission,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import formStyles from "./ApplicationForm.module.css";
import featureStyles from "./FeaturesPage.module.css";

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

// The form and the authorization switch write the same registration contract.
function applicationSettings(application?: Application) {
  return {
    display_name: application?.display_name ?? "",
    description: application?.description ?? "",
    icon: application?.icon ?? "widgets",
    version: application?.version ?? "1.0.0",
    ui_base_url: application?.ui_base_url ?? "",
    api_base_url: application?.api_base_url ?? null,
    entry_permission: application?.entry_permission ?? "read",
    display_name_by_lang: application?.display_name_by_lang ?? {},
    description_by_lang: application?.description_by_lang ?? {},
  };
}

export default function OrganizationApplications({ organizationId }: { organizationId: string }) {
  const { t } = useTranslation();
  const registry = useOrganizationApplicationsQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const [form, setForm] = useState<Application | "create" | null>(null);
  const [update, updating] = useUpdateApplicationMutation();
  const changingPermission = useRef(false);
  const [error, setError] = useState<string>();
  const authorize = async (app: Application) => {
    if (changingPermission.current) return;
    changingPermission.current = true;
    setError(undefined);
    try {
      await update({
        organizationId,
        applicationId: app.id,
        updateApplication: {
          ...applicationSettings(app),
          expected_revision: app.revision,
          enabled: !app.enabled,
        },
      }).unwrap();
    } catch (failure) {
      setError(normalizeApiError(failure).status === 409 ? "authorizationConflict" : "saveFailed");
    } finally {
      changingPermission.current = false;
    }
  };
  return (
    <>
      <div className={featureStyles.modelListToolbar}>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: "add" }}
          onClick={() => setForm("create")}
        >
          {t(`${prefix}.create`)}
        </Button>
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "help" }}
          title={t(`${prefix}.registryHint`)}
          aria-label={t(`${prefix}.help`)}
        />
      </div>
      {error && (
        <p className={featureStyles.statusError} role="alert">
          {t(`${prefix}.${error}`)}
        </p>
      )}
      {registry.isError ? (
        <p className={featureStyles.statusError} role="alert">
          {t("teamAppsPage.loadError")}
        </p>
      ) : !registry.currentData ? (
        <p className={featureStyles.status} role="status">
          {t("common.loading")}
        </p>
      ) : !registry.currentData.length ? (
        <PageEmptyState icon="widgets" message={t("rework.admin.capabilities.emptyApps")} />
      ) : (
        <DataTable
          data={registry.currentData}
          rowKey={(app) => app.id}
          size="medium"
          columns={[
            {
              label: t("rework.admin.capabilities.organizationModels.permitted"),
              size: "7rem",
              sortable: true,
              sortValue: (app) => Number(app.enabled),
              cellRenderer: (app) => (
                <div className={featureStyles.centered}>
                  <Tooltip content={t(`${prefix}.${app.enabled ? "active" : "inactive"}`)}>
                    <Switch
                      size="small"
                      checked={app.enabled}
                      disabled={updating.isLoading || registry.isFetching}
                      aria-label={t(`${prefix}.authorizeNamed`, { name: app.display_name })}
                      onChange={() => void authorize(app)}
                    />
                  </Tooltip>
                </div>
              ),
            },
            {
              label: t("rework.admin.capabilities.col.capability"),
              size: "minmax(18rem, 2fr)",
              sortable: true,
              sortValue: (app) => app.display_name,
              cellRenderer: (app) => (
                <EntityIdentity
                  name={app.display_name}
                  icon={toIconType(app.icon, "widgets")}
                  sourceId={app.logical_name}
                  version={app.version}
                  hint={app.description ? `${app.display_name}\n${app.description}` : undefined}
                  dimmed={!app.enabled}
                />
              ),
            },
            {
              label: t(`${prefix}.entry_permission`),
              size: "minmax(12rem, 1fr)",
              sortable: true,
              sortValue: (app) => t(`${prefix}.permissions.${app.entry_permission}`),
              cellRenderer: (app) => (
                <Tooltip content={t(`${prefix}.permissions.${app.entry_permission}`)} asChild>
                  <span tabIndex={0}>{t(`${prefix}.permissions.${app.entry_permission}`)}</span>
                </Tooltip>
              ),
            },
            {
              label: t("rework.admin.capabilities.organizationModels.metadata.details"),
              size: "9rem",
              cellRenderer: (app) => (
                <Button
                  color="on-surface"
                  variant="outlined"
                  size="small"
                  icon={{ category: "outlined", type: "tune" }}
                  aria-label={t(`${prefix}.editNamed`, { name: app.display_name })}
                  disabled={updating.isLoading || registry.isFetching}
                  onClick={() => setForm(app)}
                >
                  {t("rework.admin.capabilities.organizationModels.metadata.details")}
                </Button>
              ),
            },
          ]}
        />
      )}
      {form && (
        <ApplicationForm
          key={form === "create" ? "create" : form.id}
          organizationId={organizationId}
          application={form === "create" ? undefined : form}
          onClose={() => setForm(null)}
        />
      )}
    </>
  );
}

function ApplicationForm({
  organizationId,
  application,
  onClose,
}: {
  organizationId: string;
  application?: Application;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<CreateApplication>(() => ({
    logical_name: application?.logical_name ?? "",
    ...applicationSettings(application),
  }));
  const [section, setSection] = useState(0);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [error, setError] = useState<string>();
  const [create, creating] = useCreateApplicationMutation();
  const [update, updating] = useUpdateApplicationMutation();
  const saving = useRef(false);
  const busy = creating.isLoading || updating.isLoading;
  const requiredFields = ["display_name", "logical_name", "icon", "version", "ui_base_url"] as const;
  const missingFields = requiredFields.filter((field) => !draft[field]?.trim());
  const save = async () => {
    if (saving.current) return;
    setSubmitAttempted(true);
    if (missingFields.length) {
      setSection(missingFields[0] === "ui_base_url" ? 1 : 0);
      return;
    }
    saving.current = true;
    setError(undefined);
    try {
      const { logical_name, ...fields } = { ...draft, api_base_url: draft.api_base_url?.trim() || null };
      if (application)
        await update({
          organizationId,
          applicationId: application.id,
          updateApplication: {
            ...fields,
            entry_permission: fields.entry_permission ?? "read",
            expected_revision: application.revision,
            enabled: application.enabled,
          },
        }).unwrap();
      else await create({ organizationId, createApplication: { ...fields, logical_name } }).unwrap();
      onClose();
    } catch (failure) {
      const { status, code } = normalizeApiError(failure);
      setError(
        code === "application_service_owned"
          ? "dedicatedServiceRequired"
          : status === 409
            ? "conflict"
            : status === 400 || status === 422
              ? "invalid"
              : "saveFailed",
      );
    } finally {
      saving.current = false;
    }
  };
  const field = (
    name: "logical_name" | "display_name" | "description" | "version" | "ui_base_url" | "api_base_url",
  ) => {
    const required = requiredFields.some((key) => key === name);
    const error = submitAttempted && required && !draft[name]?.trim() ? t(`${prefix}.required`) : undefined;
    return (
      <TextInput
        key={name}
        label={t(`${prefix}.${name}`)}
        value={draft[name] ?? ""}
        size="small"
        required={required}
        compact={!error}
        error={error}
        disabled={busy}
        readOnly={name === "logical_name" && !!application}
        help={t(`${prefix}.${name}Hint`)}
        placeholder={
          name === "logical_name"
            ? "evaluation"
            : name === "ui_base_url"
              ? "https://application.example/ui/"
              : undefined
        }
        onChange={(event) => setDraft({ ...draft, [name]: event.target.value })}
      />
    );
  };
  const sections = ["general", "connection", "translations"] as const;
  // Preserve an existing custom icon while offering the shared supported catalogue.
  const icons: string[] = materialIcons.some((icon) => icon === draft.icon)
    ? [...materialIcons]
    : [draft.icon, ...materialIcons];
  return (
    <SettingsModal
      isOpen
      id="application-form"
      onSubmit={() => void save()}
      submitDisabled={busy || (!!application && error === "conflict")}
      title={t(`${prefix}.${application ? "edit" : "create"}`)}
      onClose={() => {
        if (!saving.current) onClose();
      }}
      actions={
        <>
          <Button color="primary" variant="outlined" size="medium" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button
            color="primary"
            variant="filled"
            size="medium"
            onClick={() => void save()}
            disabled={busy || (!!application && error === "conflict")}
          >
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className={formStyles.form}>
        <div className={formStyles.tabs}>
          <ButtonGroup
            variant="tabs"
            size="small"
            color="secondary"
            fullWidth
            aria-label={t(`${prefix}.sectionsLabel`)}
            selectedIndex={section}
            onSelectedIndexChange={setSection}
            items={sections.map((key, index) => ({
              label: t(`${prefix}.sections.${key}`),
              id: `application-tab-${key}`,
              "aria-controls": `application-panel-${key}`,
              hasError: submitAttempted && missingFields.some((field) => (field === "ui_base_url" ? 1 : 0) === index),
            }))}
          />
        </div>
        {section !== 2 && <p className={featureStyles.status}>{t(`${prefix}.requiredHint`)}</p>}
        {error && (
          <p className={featureStyles.statusError} role="alert">
            {t(`${prefix}.${error}`)}
          </p>
        )}
        <div
          className={formStyles.form}
          role="tabpanel"
          id={`application-panel-${sections[section]}`}
          aria-labelledby={`application-tab-${sections[section]}`}
        >
          {section === 0 && (
            <>
              {field("display_name")}
              {field("description")}
              <Select
                label={t(`${prefix}.icon`)}
                size="small"
                compact
                value={draft.icon}
                disabled={busy}
                help={t(`${prefix}.iconHint`)}
                search={{ placeholder: t(`${prefix}.searchIcons`), noMatchMessage: t(`${prefix}.noIcons`) }}
                options={icons.map((icon) => ({
                  value: icon,
                  key: icon,
                  label: icon.replaceAll("_", " "),
                  icon: { category: "outlined", type: toIconType(icon, "widgets") },
                }))}
                onChange={(icon) => setDraft({ ...draft, icon })}
              />
              <div className={formStyles.row}>
                {field("logical_name")}
                {field("version")}
              </div>
            </>
          )}
          {section === 1 && (
            <>
              {field("ui_base_url")}
              {field("api_base_url")}
              <Select
                label={t(`${prefix}.entry_permission`)}
                help={t(`${prefix}.entry_permissionHint`)}
                size="small"
                compact
                value={draft.entry_permission ?? "read"}
                disabled={busy}
                options={permissions.map((permission) => ({
                  value: permission,
                  key: permission,
                  label: t(`${prefix}.permissions.${permission}`),
                }))}
                onChange={(entry_permission) => setDraft({ ...draft, entry_permission })}
              />
            </>
          )}
          {section === 2 &&
            (["en", "fr"] as const).map((locale) => (
              <section key={locale} className={formStyles.form} aria-labelledby={`application-locale-${locale}`}>
                <h3 id={`application-locale-${locale}`} className={formStyles.locale}>
                  {t(`${prefix}.locale.${locale}`)}
                </h3>
                {(["display_name_by_lang", "description_by_lang"] as const).map((name) => (
                  <TextInput
                    key={name}
                    size="small"
                    compact
                    disabled={busy}
                    label={t(`${prefix}.${name}`)}
                    help={t(`${prefix}.translationsHint`)}
                    value={draft[name]?.[locale] ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, [name]: { ...draft[name], [locale]: event.target.value } })
                    }
                  />
                ))}
              </section>
            ))}
        </div>
      </div>
    </SettingsModal>
  );
}
