// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
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
  { key: "sampling_percent", label: "sampling", min: 0, max: 100, step: 1 },
  { key: "retention_days", label: "retention", min: 1, max: 3650, step: 1 },
  { key: "storage_cap_bytes", label: "storageCap", min: 1 / BYTES_PER_GB, max: 10_000, step: "any" },
] as const;
type LimitKey = (typeof LIMITS)[number]["key"];

function parseLimit(input: string, field: (typeof LIMITS)[number]) {
  const validFormat =
    field.key === "storage_cap_bytes" ? /^(?:\d+(?:\.\d{0,9})?|\.\d{1,9})$/.test(input) : /^\d+$/.test(input);
  const value = Number(input);
  if (!validFormat || value < field.min || value > field.max) return null;
  return field.key === "storage_cap_bytes" ? Math.round(value * BYTES_PER_GB) : value;
}

export default function ConversationTraceSettings({ onFlushed }: { onFlushed: () => void }) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const help = useId();
  const [draft, setDraft] = useState<Partial<Record<LimitKey, string>>>({});
  const [saveError, setSaveError] = useState(false);
  const settings = useGetConversationTraceSettingsQuery(undefined, {
    refetchOnMountOrArgChange: true,
    pollingInterval: 5000,
    skipPollingIfUnfocused: true,
  });
  const [saveSettings, saveState] = useSetConversationTraceSettingsMutation();
  const data = settings.currentData;
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
      await saveSettings({ conversationTraceSettingsUpdate: update }).unwrap();
      await settings.refetch().unwrap();
      if (reset) setDraft({});
    } catch {
      setSaveError(true);
    }
  }

  return (
    <section className={styles.captureSettings} aria-label={t("captureSettings")}>
      <div className={styles.captureSettingsHeader}>
        <div>
          <h2>{t("captureSettings")}</h2>
          <p id={help}>{t("captureHelp")}</p>
        </div>
        <Switch
          role="switch"
          aria-label={t("captureSettings")}
          aria-describedby={help}
          checked={data?.enabled ?? false}
          disabled={!data || saveState.isLoading}
          onChange={(event) => void save({ enabled: event.currentTarget.checked }, false)}
        />
      </div>
      {settings.isError && (
        <p role="alert" className={styles.error}>
          {t("settingsLoadError")}
        </p>
      )}
      {saveError && (
        <p role="alert" className={styles.error}>
          {t("settingsSaveError")}
        </p>
      )}
      {data && (
        <>
          <form
            className={styles.captureLimits}
            onSubmit={(event) => {
              event.preventDefault();
              if (!invalid && Object.keys(changed).length > 0 && !saveState.isLoading) void save(changed, true);
            }}
          >
            {fields.map((field) => (
              <TextInput
                key={field.key}
                label={t(field.label)}
                type="number"
                min={field.min}
                max={field.max}
                step={field.step}
                value={field.value}
                size="small"
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
            <Button
              type="submit"
              size="small"
              color="primary"
              variant="filled"
              disabled={invalid || !Object.keys(changed).length || saveState.isLoading}
            >
              {t("saveLimits")}
            </Button>
          </form>
          <div className={styles.captureUsage}>
            <span>{t("storedCapacity", { size: formatBytes(data.used_bytes, i18n.language) })}</span>
            <span>{t("reservedCapacity", { size: formatBytes(data.reserved_bytes, i18n.language) })}</span>
            <span className={data.degraded ? styles.error : undefined} role="status">
              {data.degradation_reason ? t(`degradation.${data.degradation_reason}`) : t("captureHealthy")}
            </span>
          </div>
          <div className={styles.captureActions}>
            <TraceDeleteButton
              mode="flush"
              disabled={saveState.isLoading}
              onDeleted={() => {
                void settings.refetch();
                onFlushed();
              }}
            />
          </div>
        </>
      )}
    </section>
  );
}
