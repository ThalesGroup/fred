// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Select from "@shared/molecules/Select/Select";
import {
  useTeamConversationRetentionQuery,
  useReplaceTeamConversationRetentionMutation,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamSettingsParameters.module.scss";

export type RetentionMode = "inherit" | "immediate" | "duration";

/** The configured seconds a mode and typed duration select, and whether the ceiling allows it. */
export function retentionChoice(mode: RetentionMode, seconds: string, ceiling: number | null | undefined) {
  // A text field: only plain digits are a duration (no sign, decimal or exponent).
  const configured =
    mode === "inherit" ? null : mode === "immediate" ? 0 : /^\d+$/.test(seconds.trim()) ? Number(seconds) : NaN;
  const valid =
    configured === null ||
    (Number.isSafeInteger(configured) &&
      configured >= (mode === "duration" ? 1 : 0) &&
      (ceiling == null || configured <= ceiling));
  return { configured, valid };
}

/** The purge delay choice, shared by the settings section and project creation. */
export function RetentionFields({
  mode,
  seconds,
  ceiling,
  inheritedFromTeamSeconds,
  disabled,
  onModeChange,
  onSecondsChange,
}: {
  mode: RetentionMode;
  seconds: string;
  ceiling: number | null | undefined;
  /** The parent team's configured delay a project follows, when the team has one. */
  inheritedFromTeamSeconds?: number;
  disabled: boolean;
  onModeChange: (mode: RetentionMode) => void;
  onSecondsChange: (seconds: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <Select<RetentionMode>
        size="medium"
        label={t("rework.teamRetention.mode")}
        value={mode}
        disabled={disabled}
        options={(["inherit", "immediate", "duration"] as const).map((value) => ({
          key: value,
          value,
          // A project without its own value follows its team's configured delay.
          label:
            value === "inherit" && inheritedFromTeamSeconds !== undefined
              ? t("rework.teamRetention.inheritTeam", { seconds: inheritedFromTeamSeconds })
              : t(`rework.teamRetention.${value}`),
        }))}
        onChange={onModeChange}
      />
      {mode === "duration" && (
        <div className={styles.seconds}>
          <TextInput
            inputMode="numeric"
            label={t("rework.teamRetention.seconds")}
            value={seconds}
            disabled={disabled}
            error={!retentionChoice(mode, seconds, ceiling).valid ? t("rework.teamRetention.invalid") : undefined}
            onChange={(event) => onSecondsChange(event.target.value)}
          />
        </div>
      )}
    </>
  );
}

export default function TeamConversationRetention({ spaceId, allowed }: { spaceId: string; allowed: boolean }) {
  const { t } = useTranslation();
  const query = useTeamConversationRetentionQuery({ id: spaceId }, { skip: !allowed, refetchOnMountOrArgChange: true });
  const [replace, mutation] = useReplaceTeamConversationRetentionMutation();
  const [draftMode, setMode] = useState<RetentionMode>();
  const [draftSeconds, setSeconds] = useState<string>();
  const [error, setError] = useState(false);
  const [saved, setSaved] = useState(false);
  const data = query.currentData;
  const mode =
    draftMode ??
    (data?.configured_seconds == null ? "inherit" : data.configured_seconds === 0 ? "immediate" : "duration");
  const seconds = draftSeconds ?? String(data?.configured_seconds ?? data?.effective_seconds ?? "");
  const { configured, valid } = retentionChoice(mode, seconds, data?.organization_ceiling_seconds);
  const busy = !allowed || query.isFetching || query.isError || mutation.isLoading;
  const save = async () => {
    if (busy || !valid || !data) return;
    setError(false);
    setSaved(false);
    try {
      await replace({ id: spaceId, replaceConversationRetention: { configured_seconds: configured } }).unwrap();
      await query.refetch().unwrap();
      setMode(undefined);
      setSeconds(undefined);
      setSaved(true);
    } catch {
      setError(true);
    }
  };
  return (
    <section className={styles.section}>
      <h2>{t("rework.teamRetention.title")}</h2>
      <p>{t("rework.teamRetention.explanation")}</p>
      {query.isError ? (
        <p role="alert">{t("rework.manager.unavailable")}</p>
      ) : !data ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <>
          <p>{t("rework.teamRetention.effective", { seconds: data.effective_seconds })}</p>
          <p>
            {data.organization_ceiling_seconds == null
              ? t("rework.teamRetention.noCeiling")
              : t("rework.teamRetention.ceiling", { seconds: data.organization_ceiling_seconds })}
          </p>
          <RetentionFields
            mode={mode}
            seconds={seconds}
            ceiling={data.organization_ceiling_seconds}
            inheritedFromTeamSeconds={data.inherited_from_team ? data.inherited_seconds : undefined}
            disabled={busy}
            onModeChange={(value) => {
              setMode(value);
              setSaved(false);
            }}
            onSecondsChange={(value) => {
              setSeconds(value);
              setSaved(false);
            }}
          />
          {error && <p role="alert">{t("rework.teamRetention.failed")}</p>}
          {saved && <p role="status">{t("rework.teamRetention.saved")}</p>}
          <Button
            color="primary"
            variant="filled"
            size="small"
            disabled={busy || !valid || configured === data.configured_seconds}
            onClick={() => void save()}
          >
            {t("common.save")}
          </Button>
        </>
      )}
    </section>
  );
}
