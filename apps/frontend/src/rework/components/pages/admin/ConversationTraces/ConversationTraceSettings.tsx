// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useConversationTraceAccess } from "@core/hooks/useConversationTraceAccess";
import { useNavigate } from "react-router-dom";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
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
  { key: "storage_cap_bytes", label: "storageCap", min: 1 / BYTES_PER_GB, max: 10_000, step: "any" },
  { key: "retention_days", label: "retention", min: 1, max: 3650, step: 1 },
  { key: "sampling_percent", label: "sampling", min: 0, max: 100, step: 1 },
] as const;
type LimitKey = (typeof LIMITS)[number]["key"];

function parseLimit(input: string, field: (typeof LIMITS)[number]) {
  const validFormat =
    field.key === "storage_cap_bytes" ? /^(?:\d+(?:\.\d{0,9})?|\.\d{1,9})$/.test(input) : /^\d+$/.test(input);
  const value = Number(input);
  if (!validFormat || value < field.min || value > field.max) return null;
  return field.key === "storage_cap_bytes" ? Math.round(value * BYTES_PER_GB) : value;
}

export default function ConversationTraceSettings({
  settings,
  onClose,
  onFlushed,
}: {
  settings: ReturnType<typeof useGetConversationTraceSettingsQuery>;
  onClose: () => void;
  onFlushed: () => void;
}) {
  const { organizationId } = useConversationTraceAccess();
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const help = useId();
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
    <Dialog
      open
      title={t("captureSettings")}
      confirmLabel={t("saveLimits")}
      onConfirm={() => void save(changed, true)}
      confirmDisabled={!data || invalid || !Object.keys(changed).length || saveState.isLoading}
      cancelLabel={t("closeSettings")}
      onCancel={() => {
        if (!saveState.isLoading) onClose();
      }}
      dismissible={!saveState.isLoading}
    >
      <div className={styles.dialogFields}>
        <div className={styles.settingLine}>
          <span>{t("enableCapture")}</span>
          <Switch
            role="switch"
            aria-label={t("captureSettings")}
            aria-describedby={help}
            checked={data?.enabled ?? false}
            disabled={!data || saveState.isLoading}
            onChange={(event) => void save({ enabled: event.currentTarget.checked }, false)}
          />
        </div>
        <p id={help}>{t("captureHelp")}</p>
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
            <div className={styles.storageUsage}>
              <strong>{t("storageUsage")}</strong>
              <span>
                {t("storageUsedOfCap", {
                  used: formatBytes(data.used_bytes, i18n.language, "decimal"),
                  cap: formatBytes(data.storage_cap_bytes, i18n.language, "decimal"),
                })}
              </span>
              <meter
                aria-label={t("storageUsage")}
                max={data.storage_cap_bytes}
                value={Math.min(data.used_bytes, data.storage_cap_bytes)}
              />
              <span>{t("reservedCapacity", { size: formatBytes(data.reserved_bytes, i18n.language, "decimal") })}</span>
              <span className={data.degraded ? styles.error : undefined} role="status">
                {data.degradation_reason ? t(`degradation.${data.degradation_reason}`) : t("captureHealthy")}
              </span>
            </div>
            <div className={styles.settingsInputs}>
              {fields.map((field) => (
                <TextInput
                  key={field.key}
                  label={t(field.label)}
                  type="number"
                  min={field.min}
                  max={field.max}
                  step={field.step}
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
      </div>
    </Dialog>
  );
}

export function ConversationTraceSettingsPage() {
  const { organizationId, canManage } = useConversationTraceAccess();
  const navigate = useNavigate();
  const settings = useGetConversationTraceSettingsQuery(
    { organizationId },
    { skip: !canManage, refetchOnMountOrArgChange: true },
  );
  return (
    <ConversationTraceSettings
      key={organizationId}
      settings={settings}
      onClose={() => navigate("/admin", { replace: true })}
      onFlushed={() => void settings.refetch()}
    />
  );
}
