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

type Mode = "inherit" | "immediate" | "duration";
export default function TeamConversationRetention({ spaceId, allowed }: { spaceId: string; allowed: boolean }) {
  const { t } = useTranslation();
  const query = useTeamConversationRetentionQuery({ id: spaceId }, { skip: !allowed, refetchOnMountOrArgChange: true });
  const [replace, mutation] = useReplaceTeamConversationRetentionMutation();
  const [draftMode, setMode] = useState<Mode>();
  const [draftSeconds, setSeconds] = useState<string>();
  const [error, setError] = useState(false);
  const [saved, setSaved] = useState(false);
  const data = query.currentData;
  const mode =
    draftMode ??
    (data?.configured_seconds == null ? "inherit" : data.configured_seconds === 0 ? "immediate" : "duration");
  const seconds = draftSeconds ?? String(data?.configured_seconds ?? data?.effective_seconds ?? "");
  const configured = mode === "inherit" ? null : mode === "immediate" ? 0 : Number(seconds);
  const valid =
    configured === null ||
    (Number.isSafeInteger(configured) &&
      configured >= (mode === "duration" ? 1 : 0) &&
      (data?.organization_ceiling_seconds == null || configured <= data.organization_ceiling_seconds));
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
          <Select<Mode>
            size="medium"
            label={t("rework.teamRetention.mode")}
            value={mode}
            disabled={busy}
            options={(["inherit", "immediate", "duration"] as const).map((value) => ({
              key: value,
              value,
              // A project without its own value follows its team's configured delay.
              label:
                value === "inherit" && data.inherited_from_team
                  ? t("rework.teamRetention.inheritTeam", { seconds: data.inherited_seconds })
                  : t(`rework.teamRetention.${value}`),
            }))}
            onChange={(value) => {
              setMode(value);
              setSaved(false);
            }}
          />
          {mode === "duration" && (
            <TextInput
              type="number"
              label={t("rework.teamRetention.seconds")}
              min={1}
              max={data.organization_ceiling_seconds ?? undefined}
              step={1}
              value={seconds}
              disabled={busy}
              error={!valid ? t("rework.teamRetention.invalid") : undefined}
              onChange={(event) => {
                setSeconds(event.target.value);
                setSaved(false);
              }}
            />
          )}
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
