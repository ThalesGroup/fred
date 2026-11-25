// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useConversationTraceAccess } from "@core/hooks/useConversationTraceAccess";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import { formatBytes } from "@shared/utils/formatBytes";
import {
  type ConversationTraceSettingsUpdate,
  useGetConversationTraceSettingsQuery,
  useSetConversationTraceSettingsMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ConversationTraces.module.css";
import { TRACE_TRANSLATION_PREFIX } from "./traceControls";
import { TraceDeleteButton } from "./TraceDeleteButton";

const BYTES_PER_GB = 1_000_000_000;
const LIMITS = [
  { key: "storage_cap_bytes", label: "storageCap", min: 1 / BYTES_PER_GB, max: 10_000, inputMode: "decimal" },
  { key: "retention_days", label: "retention", min: 1, max: 3650, inputMode: "numeric" },
  { key: "sampling_percent", label: "sampling", min: 0, max: 100, inputMode: "numeric" },
] as const;
type LimitKey = (typeof LIMITS)[number]["key"];

function parseLimit(raw: string, field: (typeof LIMITS)[number]) {
  // A text field, so a French decimal comma is accepted like the dot.
  const input = field.key === "storage_cap_bytes" ? raw.replace(",", ".") : raw;
  const validFormat =
    field.key === "storage_cap_bytes" ? /^(?:\d+(?:\.\d{0,9})?|\.\d{1,9})$/.test(input) : /^\d+$/.test(input);
  const value = Number(input);
  if (!validFormat || value < field.min || value > field.max) return null;
  return field.key === "storage_cap_bytes" ? Math.round(value * BYTES_PER_GB) : value;
}

/** Organization trace capture: switch, storage usage, limits and purge, on its own admin page. */
export default function ConversationTraceSettingsPage() {
  const { organizationId } = useConversationTraceAccess();
  return <CaptureSettings key={organizationId} />;
}

function CaptureSettings() {
  const { organizationId, canManage } = useConversationTraceAccess();
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const help = useId();
  const settings = useGetConversationTraceSettingsQuery(
    { organizationId },
    { skip: !canManage, refetchOnMountOrArgChange: true },
  );
  const [draft, setDraft] = useState<Partial<Record<LimitKey, string>>>({});
  const [saveError, setSaveError] = useState(false);
  const [saveSettings, saveState] = useSetConversationTraceSettingsMutation();
  const data = settings.isError ? undefined : settings.currentData;
  const changed: ConversationTraceSettingsUpdate = {};
  let invalid = false;
  const fields = LIMITS.map((field) => {
    const saved = data?.[field.key];
    const fallback =
      saved === undefined
        ? ""
        : field.key === "storage_cap_bytes"
          ? (saved / BYTES_PER_GB).toFixed(9).replace(/\.?0+$/, "")
          : String(saved);
    const value = draft[field.key] ?? fallback;
    const parsed = parseLimit(value, field);
    const invalidField = draft[field.key] !== undefined && parsed === null;
    if (parsed !== null && parsed !== saved) changed[field.key] = parsed;
    invalid ||= invalidField;
    return { ...field, value, invalid: invalidField };
  });

  async function save(update: ConversationTraceSettingsUpdate, reset: boolean) {
    setSaveError(false);
    try {
      await saveSettings({ organizationId, conversationTraceSettingsUpdate: update }).unwrap();
      await settings.refetch().unwrap();
      if (reset) setDraft({});
    } catch {
      setSaveError(true);
    }
  }

  return (
    <div className={styles.page}>
      <PageHeader title={t("captureSettings")} />
      <div className={styles.settingsBody}>
        {settings.isError && (
          <span role="alert" className={styles.error}>
            {t("settingsLoadError")}
          </span>
        )}
        {saveError && (
          <span role="alert" className={styles.error}>
            {t("settingsSaveError")}
          </span>
        )}
        <section className={styles.settingsSection}>
          <div className={styles.settingLine}>
            <span>{t("enableCapture")}</span>
            <Switch
              role="switch"
              aria-label={t("enableCapture")}
              aria-describedby={help}
              checked={data?.enabled ?? false}
              disabled={!data || saveState.isLoading}
              onChange={(event) => void save({ enabled: event.currentTarget.checked }, false)}
            />
          </div>
          <span id={help} className={styles.settingsHint}>
            {t("captureHelp")}
          </span>
        </section>
        {data && (
          <>
            <section className={styles.settingsSection}>
              <div className={styles.storageUsage}>
                <h2>{t("storageUsage")}</h2>
                <span>
                  {t("storageUsedOfCap", {
                    used: formatBytes(data.used_bytes, i18n.language, "decimal"),
                    cap: formatBytes(data.storage_cap_bytes, i18n.language, "decimal"),
                  })}
                </span>
              </div>
              <meter
                aria-label={t("storageUsage")}
                max={data.storage_cap_bytes}
                value={Math.min(data.used_bytes, data.storage_cap_bytes)}
              />
              <span className={styles.settingsHint}>
                {t("reservedCapacity", { size: formatBytes(data.reserved_bytes, i18n.language, "decimal") })}
              </span>
              <span className={data.degraded ? styles.error : undefined} role="status">
                {data.degradation_reason ? t(`degradation.${data.degradation_reason}`) : t("captureHealthy")}
              </span>
              <div className={styles.sectionAction}>
                <TraceDeleteButton
                  mode="flush"
                  disabled={saveState.isLoading}
                  onDeleted={() => void settings.refetch()}
                />
              </div>
            </section>
            <section className={styles.settingsSection}>
              <div className={styles.limitFields}>
                {fields.map((field) => (
                  <TextInput
                    key={field.key}
                    label={t(field.label)}
                    inputMode={field.inputMode}
                    value={field.value}
                    size="medium"
                    compact={!field.invalid}
                    showCharacterCount={false}
                    disabled={saveState.isLoading}
                    error={field.invalid ? t(`${field.label}Invalid`) : undefined}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setDraft((previous) => ({ ...previous, [field.key]: value }));
                    }}
                  />
                ))}
              </div>
              <Button
                color="primary"
                variant="filled"
                size="small"
                disabled={!data || invalid || !Object.keys(changed).length || saveState.isLoading}
                onClick={() => void save(changed, true)}
              >
                {t("saveLimits")}
              </Button>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
