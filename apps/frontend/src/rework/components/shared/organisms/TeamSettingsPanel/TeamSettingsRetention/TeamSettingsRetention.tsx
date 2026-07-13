// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Data & Retention tab (CTRLP-12 R3). The retention window *is* the evaluation
// window (RFC §4): a conversation stays available for the team to evaluate on
// real usage for exactly this long, then it is provably erased. The platform
// sets a maximum cap (read-only); the owner may only *tighten* it below the cap.
// Resolution and the cap clamp live server-side (retention resolver); a team
// value above the cap returns HTTP 422, surfaced here as an inline "exceeds the
// platform cap".
//
// R3: retention is now folded into team_metadata. It is READ off the already
// fetched team record (`team.retention`, embedded on TeamWithPermissions) and
// WRITTEN through the existing team PATCH endpoint (`team_delete_grace`/
// `max_idle` on UpdateTeamRequest) — no dedicated /retention endpoints. The
// control is a *preview*: the settings persist but expiry-time erasure is not
// enforced until Phase E ships, hence the caption below.

import styles from "./TeamSettingsRetention.module.scss";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useUpdateTeamMutation } from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";

interface TeamSettingsRetentionProps {
  team: TeamWithPermissions;
}

// The two governed retention fields, in the order the resolver exposes them.
const RETENTION_FIELDS = [
  {
    key: "team_delete_grace",
    labelKey: "rework.teamSettings.retention.fields.teamDeleteGrace",
    descKey: "rework.teamSettings.retention.fields.teamDeleteGraceDesc",
  },
  {
    key: "max_idle",
    labelKey: "rework.teamSettings.retention.fields.maxIdle",
    descKey: "rework.teamSettings.retention.fields.maxIdleDesc",
  },
] as const;

type RetentionFieldKey = (typeof RETENTION_FIELDS)[number]["key"];
type RetentionForm = Record<RetentionFieldKey, string>;

export default function TeamSettingsRetention({ team }: TeamSettingsRetentionProps) {
  const { t } = useTranslation();
  // Retention is embedded on the already-fetched team record (R3). Writing goes
  // through the team PATCH endpoint, which invalidates the team tag and refetches
  // this record — so the resolved view here stays in sync after a save.
  const retention = team.retention;
  const [updateTeam] = useUpdateTeamMutation();

  // Editing the per-team value is owner-only, matching the backend gate
  // (CAN_UPDATE_INFO). Non-owners see both columns read-only. The platform cap is
  // always read-only regardless of permission.
  const { canUpdateInfo: canEdit } = useTeamCapabilities(team);

  const { register, getValues, reset, setError, clearErrors, formState } = useForm<RetentionForm>({
    defaultValues: { team_delete_grace: "", max_idle: "" },
  });

  useEffect(() => {
    if (!retention) return;
    reset({
      team_delete_grace: retention.team_delete_grace.team_value ?? "",
      max_idle: retention.max_idle.team_value ?? "",
    });
  }, [retention, reset]);

  const handleSave = async (field: RetentionFieldKey) => {
    if (!retention) return;
    const next = getValues()[field].trim();
    const current = retention[field].team_value ?? "";
    if (next === current) return;

    clearErrors(field);
    try {
      // Partial PATCH: an empty value clears the override (re-inherit the cap).
      await updateTeam({
        teamId: team.id,
        updateTeamRequest: { [field]: next === "" ? null : next },
      }).unwrap();
    } catch (error) {
      const status = (error as { status?: number }).status;
      setError(field, {
        message:
          status === 422 ? t("rework.teamSettings.retention.exceedsCap") : t("rework.teamSettings.retention.saveError"),
      });
    }
  };

  return (
    <div className={styles["team-settings-retention-container"]}>
      <span className={styles["preview-caption"]}>{t("rework.teamSettings.retention.enforcementNotice")}</span>
      {RETENTION_FIELDS.map(({ key, labelKey, descKey }) => {
        const field = retention?.[key];
        return (
          <div className={styles["form-section"]} key={key}>
            <span className={styles["field-title"]}>{t(labelKey)}</span>
            <span className={styles["field-hint"]}>{t(descKey)}</span>
            <div className={styles["field-row"]}>
              <TextInput
                label={t("rework.teamSettings.retention.platformCap")}
                value={field?.platform_max ?? "—"}
                disabled
                readOnly
              />
              <TextInput
                label={t("rework.teamSettings.retention.teamValue")}
                explanation={field?.platform_max ? t("rework.teamSettings.retention.teamValueHint") : undefined}
                error={formState.errors[key]?.message}
                placeholder={field?.platform_max ?? ""}
                disabled={!canEdit}
                {...register(key, { onBlur: () => handleSave(key) })}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
