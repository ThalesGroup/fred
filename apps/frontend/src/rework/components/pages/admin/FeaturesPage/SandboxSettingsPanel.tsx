// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useGetSandboxSettingsControlPlaneV1AdminPlatformSandboxSettingsGetQuery,
  usePutSandboxSettingsControlPlaneV1AdminPlatformSandboxSettingsPutMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./SandboxSettingsPanel.module.css";

interface Props {
  visible: boolean;
}

export function SandboxSettingsPanel({ visible }: Props) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { data, isLoading, isError, refetch } = useGetSandboxSettingsControlPlaneV1AdminPlatformSandboxSettingsGetQuery(
    undefined,
    {
      skip: !visible,
    },
  );
  const [save, { isLoading: isSaving }] = usePutSandboxSettingsControlPlaneV1AdminPlatformSandboxSettingsPutMutation();
  const [idle, setIdle] = useState("20");
  const [active, setActive] = useState("8");
  const [warm, setWarm] = useState("0");
  const [validationError, setValidationError] = useState(false);

  useEffect(() => {
    if (!data) return;
    setIdle(String(data.idle_minutes));
    setActive(String(data.max_active_sessions));
    setWarm(String(data.warm_capacity));
  }, [data]);

  if (!visible) return null;

  const submit = async () => {
    const values = [Number(idle), Number(active), Number(warm)];
    if (
      [idle, active, warm].some((value) => value.trim() === "") ||
      values.some((value) => !Number.isInteger(value)) ||
      values[0] < 1 ||
      values[0] > 120 ||
      values[1] < 1 ||
      values[1] > 1000 ||
      values[2] < 0 ||
      values[2] > 1000
    ) {
      setValidationError(true);
      return;
    }
    setValidationError(false);
    try {
      await save({
        sandboxSettingsUpdate: {
          idle_minutes: values[0],
          max_active_sessions: values[1],
          warm_capacity: values[2],
        },
      }).unwrap();
      await refetch();
      showSuccess({ summary: t("rework.admin.sandboxSettings.saved") });
    } catch {
      showError({ summary: t("rework.admin.sandboxSettings.saveError") });
    }
  };

  return (
    <section className={styles.panel} aria-label={t("rework.admin.sandboxSettings.title")}>
      <div className={styles.intro}>
        <h2>{t("rework.admin.sandboxSettings.title")}</h2>
        <p>{t("rework.admin.sandboxSettings.description")}</p>
        {data && data.profile_id !== "unconfigured" && (
          <p>
            {t("rework.admin.sandboxSettings.profile")}: <strong>{data.profile_id}</strong>
          </p>
        )}
        {data?.profile_id === "unconfigured" && <p>{t("rework.admin.sandboxSettings.profileUnconfigured")}</p>}
      </div>
      {isLoading && <p>{t("rework.admin.sandboxSettings.loading")}</p>}
      {isError && <p role="alert">{t("rework.admin.sandboxSettings.loadError")}</p>}
      {data && (
        <div className={styles.controls}>
          <TextInput
            label={t("rework.admin.sandboxSettings.idle")}
            explanation={t("rework.admin.sandboxSettings.idleHelp")}
            type="number"
            min={1}
            max={120}
            value={idle}
            onChange={(event) => setIdle(event.target.value)}
          />
          <TextInput
            label={t("rework.admin.sandboxSettings.active")}
            explanation={t("rework.admin.sandboxSettings.activeHelp")}
            type="number"
            min={1}
            max={1000}
            value={active}
            onChange={(event) => setActive(event.target.value)}
          />
          <TextInput
            label={t("rework.admin.sandboxSettings.warm")}
            explanation={t("rework.admin.sandboxSettings.warmHelp")}
            type="number"
            min={0}
            max={1000}
            value={warm}
            onChange={(event) => setWarm(event.target.value)}
          />
          {validationError && <p role="alert">{t("rework.admin.sandboxSettings.invalid")}</p>}
          <Button color="primary" variant="filled" size="small" onClick={submit} disabled={isSaving}>
            {t("rework.admin.sandboxSettings.save")}
          </Button>
        </div>
      )}
    </section>
  );
}
