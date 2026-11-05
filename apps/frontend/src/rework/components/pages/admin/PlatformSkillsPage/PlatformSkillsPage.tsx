// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import { normalizeApiError } from "@rework/core/errors/normalizeApiError";
import { skillPresentation } from "@rework/utils/skillPresentation";
import {
  useGetSkillsQuery,
  useSetSkillMutation,
  type PlatformSkillEntry,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PlatformSkillsPage.module.css";

export default function PlatformSkillsPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, isFetching, refetch } = useGetSkillsQuery(undefined, {
    refetchOnMountOrArgChange: true,
  });
  const [setSkill] = useSetSkillMutation();
  const [savingName, setSavingName] = useState<string | null>(null);
  const [focusedName, setFocusedName] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const sourceUnverified = Boolean(data?.unavailable_runtime_ids.length || data?.unsupported_runtime_ids.length);
  const absentDisabled = (data?.disabled_skill_names ?? []).filter(
    (name) => !data?.skills.some((entry) => entry.skill.name === name),
  );

  const applyEnabled = async (name: string, enabled: boolean) => {
    if (inFlight.current || isFetching || (!enabled && sourceUnverified)) return;
    inFlight.current = true;
    setSavingName(name);
    setSaveError(null);
    try {
      await setSkill({ name, setSkillEnabled: { enabled } }).unwrap();
      const result = await refetch();
      if (result.error) setSaveError("rework.admin.skills.refreshAfterSaveError");
    } catch (error) {
      const status = normalizeApiError(error).status;
      setSaveError(
        status === 409
          ? "rework.admin.skills.saveUnsupported"
          : status === 503
            ? "rework.admin.skills.saveUnavailable"
            : "rework.admin.skills.saveError",
      );
      await refetch();
    } finally {
      inFlight.current = false;
      setSavingName(null);
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
          skill.user_invocable ? t("rework.admin.skills.userInvocable") : null,
          !skill.disable_model_invocation ? t("rework.admin.skills.modelInvocable") : null,
        ]
          .filter(Boolean)
          .join(", ") || t("rework.admin.skills.noInvocation"),
    },
    {
      label: t("rework.admin.skills.sources"),
      size: "1fr",
      cellRenderer: ({ runtime_ids }) => runtime_ids.join(", "),
    },
    {
      label: t("rework.admin.skills.enabled"),
      size: "0.7fr",
      cellRenderer: (entry) => {
        const locked = savingName !== null || isFetching || (entry.enabled && sourceUnverified);
        return (
          <Switch
            size="small"
            checked={entry.enabled}
            disabled={locked && focusedName !== entry.skill.name && savingName !== entry.skill.name}
            aria-disabled={locked || undefined}
            onFocus={() => setFocusedName(entry.skill.name)}
            onBlur={() => setFocusedName(null)}
            aria-label={t("rework.admin.skills.toggle", { name: skillPresentation(t, entry.skill).title })}
            title={entry.enabled && sourceUnverified ? t("rework.admin.skills.disableBlocked") : undefined}
            onChange={() => void applyEnabled(entry.skill.name, !entry.enabled)}
          />
        );
      },
    },
  ];

  return (
    <div className={styles.page} aria-busy={savingName !== null || isFetching}>
      <PageHeader title={t("rework.admin.skills.title")} subtitle={t("rework.admin.skills.scope")} />
      <div className={styles.toolbar}>
        <p>{t("rework.admin.skills.effect")}</p>
        <Button
          size="small"
          variant="outlined"
          color="on-surface"
          icon={{ category: "outlined", type: "refresh" }}
          disabled={isFetching || savingName !== null}
          onClick={() => void refetch()}
        >
          {t("rework.admin.skills.refresh")}
        </Button>
      </div>
      {saveError && (
        <p role="alert" className={styles.error}>
          {t(saveError)}
        </p>
      )}
      {isLoading && <p role="status">{t("rework.admin.skills.loading")}</p>}
      {isError && (
        <p role="alert" className={styles.error}>
          {t("rework.admin.skills.loadError")}
        </p>
      )}
      {data && !isError && (
        <>
          {data.unavailable_runtime_ids.length > 0 && (
            <p role="status" className={styles.warning}>
              {t("rework.admin.skills.unavailableSources", { runtimes: data.unavailable_runtime_ids.join(", ") })}
            </p>
          )}
          {data.unsupported_runtime_ids.length > 0 && (
            <p role="status" className={styles.warning}>
              {t("rework.admin.skills.unsupportedSources", { runtimes: data.unsupported_runtime_ids.join(", ") })}
            </p>
          )}
          {data.disabled_runtime_ids.length > 0 && (
            <p role="status" className={styles.notice}>
              {t("rework.admin.skills.disabledSources", { runtimes: data.disabled_runtime_ids.join(", ") })}
            </p>
          )}
          {data.custom_runtime_ids.length > 0 && (
            <p role="status" className={styles.notice}>
              {t("rework.admin.skills.customSources", { runtimes: data.custom_runtime_ids.join(", ") })}
            </p>
          )}
          {data.conflicting_skill_names.length > 0 && (
            <p role="status" className={styles.warning}>
              {t("rework.admin.skills.conflictingMetadata", { skills: data.conflicting_skill_names.join(", ") })}
            </p>
          )}
          {data.skills.length > 0 ? (
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
                    <code>/{name}</code>
                    <Button
                      size="small"
                      variant="outlined"
                      color="on-surface"
                      disabled={savingName !== null || isFetching}
                      onClick={() => void applyEnabled(name, true)}
                    >
                      {t("rework.admin.skills.restore", { name })}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
