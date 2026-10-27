// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.

import { useTranslation } from "react-i18next";
import { useRef, useState } from "react";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import {
  useGetPlatformSkillsQuery,
  useSetPlatformSkillEnabledMutation,
  type PlatformSkillEntry,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { skillPresentation } from "@rework/utils/skillPresentation";
import { normalizeApiError } from "@rework/core/errors/normalizeApiError";
import styles from "./PlatformSkillsPanel.module.css";

export function PlatformSkillsPanel() {
  const { t } = useTranslation();
  const { data, isLoading, isError, isFetching, refetch } = useGetPlatformSkillsQuery(undefined, {
    refetchOnMountOrArgChange: true,
  });
  const [setEnabled] = useSetPlatformSkillEnabledMutation();
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const sourceUnverified = Boolean(data?.unavailable_runtime_ids.length || data?.unsupported_runtime_ids.length);
  const absentDisabled = (data?.disabled_skill_names ?? []).filter(
    (name) => !data.skills.some((entry) => entry.skill.name === name),
  );
  const applyEnabled = async (name: string, enabled: boolean) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      await setEnabled({ skillName: name, setPlatformSkillEnabledRequest: { enabled } }).unwrap();
      const result = await refetch();
      if (result.error) setSaveError("rework.admin.skills.refreshAfterSaveError");
    } catch (error) {
      const failure = normalizeApiError(error);
      setSaveError(
        failure.status === 409
          ? "rework.admin.skills.saveUnsupported"
          : failure.status === 503
            ? "rework.admin.skills.saveUnavailable"
            : "rework.admin.skills.saveError",
      );
      await refetch();
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };
  const columns: DataTableColumn<PlatformSkillEntry>[] = [
    {
      label: t("rework.admin.skills.skill"),
      size: "1.3fr",
      cellRenderer: ({ skill }) => (
        <div className={styles.identity}>
          <span>{skillPresentation(t, skill).title}</span>
          <code>/{skill.name}</code>
        </div>
      ),
    },
    {
      label: t("rework.admin.skills.description"),
      size: "2fr",
      cellRenderer: ({ skill }) => skillPresentation(t, skill).description,
    },
    {
      label: t("rework.admin.skills.invocation"),
      size: "1.2fr",
      cellRenderer: ({ skill }) =>
        [
          skill.user_invocable !== false ? t("rework.admin.skills.userInvocable") : null,
          !skill.disable_model_invocation ? t("rework.admin.skills.modelInvocable") : null,
        ]
          .filter(Boolean)
          .join(", ") || t("rework.admin.skills.noInvocation"),
    },
    {
      label: t("rework.admin.skills.sources"),
      size: "1fr",
      cellRenderer: (entry) => entry.runtime_ids.join(", "),
    },
    {
      label: t("rework.admin.skills.enabled"),
      size: "0.7fr",
      cellRenderer: (entry) => (
        <Switch
          size="small"
          checked={entry.enabled}
          disabled={saving || isFetching || (entry.enabled && sourceUnverified)}
          aria-label={t("rework.admin.skills.toggle", { name: skillPresentation(t, entry.skill).title })}
          title={entry.enabled && sourceUnverified ? t("rework.admin.skills.disableBlocked") : undefined}
          onChange={() => void applyEnabled(entry.skill.name, !entry.enabled)}
        />
      ),
    },
  ];
  return (
    <section className={styles.panel} aria-label={t("rework.admin.skills.title")} aria-busy={saving || isFetching}>
      <div className={styles.toolbar}>
        <p>{t("rework.admin.skills.scope")}</p>
        <Button
          size="small"
          variant="outlined"
          color="on-surface"
          icon={{ category: "outlined", type: "refresh" }}
          disabled={isFetching || saving}
          onClick={() => void refetch()}
        >
          {t("rework.admin.skills.refresh")}
        </Button>
      </div>
      <p className={styles.effect}>{t("rework.admin.skills.effect")}</p>
      {saveError && <p role="alert">{t(saveError)}</p>}
      {isLoading ? (
        <p role="status">{t("rework.admin.skills.loading")}</p>
      ) : isError ? (
        <p role="alert">{t("rework.admin.skills.loadError")}</p>
      ) : data ? (
        <>
          {Boolean(data.unavailable_runtime_ids.length) && (
            <p role="status" className={styles.warning}>
              {t("rework.admin.skills.unavailableSources", { runtimes: data.unavailable_runtime_ids.join(", ") })}
            </p>
          )}
          {Boolean(data.unsupported_runtime_ids.length) && (
            <p role="status" className={styles.warning}>
              {t("rework.admin.skills.unsupportedSources", { runtimes: data.unsupported_runtime_ids.join(", ") })}
            </p>
          )}
          {data.skills.length ? (
            <DataTable columns={columns} data={data.skills} rowKey={(entry) => entry.skill.name} size="medium" />
          ) : (
            <p role="status">{t("rework.admin.skills.empty")}</p>
          )}
          {absentDisabled.length > 0 && (
            <div className={styles.recovery}>
              <p>{t("rework.admin.skills.absentDisabled")}</p>
              <ul>
                {absentDisabled.map((name) => (
                  <li key={name}>
                    <span>
                      {skillPresentation(t, { name, builtin: true }).title} <code>/{name}</code>
                    </span>
                    <Button
                      size="small"
                      variant="outlined"
                      color="on-surface"
                      disabled={saving || isFetching}
                      onClick={() => void applyEnabled(name, true)}
                    >
                      {t("rework.admin.skills.restore", { name: skillPresentation(t, { name, builtin: true }).title })}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
