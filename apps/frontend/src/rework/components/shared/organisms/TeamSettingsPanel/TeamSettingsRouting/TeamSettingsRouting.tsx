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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import Button from "@shared/atoms/Button/Button.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { rowForProfile, teamModelRows, type TeamModelRow } from "@rework/features/capabilities/teamModelRows";
import type {
  DisableImpact,
  TeamWithPermissions,
  UpdateTeamRoutingPolicyRequest,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAvailableModelProfilesQuery,
  useLazyDisableImpactQuery,
  useTeamRoutingPolicyQuery,
  useUpdateTeamRoutingPolicyMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamSettingsRouting.module.scss";

interface TeamSettingsRoutingProps {
  team: TeamWithPermissions;
  /** Team admins (and a personal space's owner) write; editors and analysts read. */
  canWrite: boolean;
}

type PendingDisable = { row: TeamModelRow; impact?: DisableImpact; failed?: boolean };

/**
 * The team's Models section: one row per model the platform allows the team,
 * with the default, the enable switch and the reasoning default. Each change
 * is saved at once, like the platform UI themes page.
 */
export default function TeamSettingsRouting({ team, canWrite }: TeamSettingsRoutingProps) {
  const { t } = useTranslation();
  const { showWarn } = useToast();
  const {
    data: policy,
    isLoading,
    isFetching: isFetchingPolicy,
    isError: policyError,
    refetch: refetchPolicy,
  } = useTeamRoutingPolicyQuery({ teamId: team.id });
  const {
    data: availableModels,
    isLoading: isLoadingModels,
    isFetching: isFetchingModels,
    isError: modelsError,
  } = useAvailableModelProfilesQuery({ teamId: team.id });
  const [updateRoutingPolicy, { isLoading: isSaving }] = useUpdateTeamRoutingPolicyMutation();
  const [fetchDisableImpact] = useLazyDisableImpactQuery();
  const [pendingDisable, setPendingDisable] = useState<PendingDisable | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (isLoading || isLoadingModels) return null;
  if (policyError || modelsError) {
    return (
      <div className={styles.page}>
        <PageHeader
          title={t("rework.teamSettings.routing.title")}
          subtitle={t("rework.teamSettings.routing.subtitle")}
        />
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.teamSettings.routing.loadError")}
          description={t("rework.teamSettings.routing.loadErrorHint")}
        />
      </div>
    );
  }

  const profiles = availableModels?.profiles ?? [];
  const storedDefault = policy?.chat_default_profile_id ?? null;
  const effectiveDefault = storedDefault ?? availableModels?.effective_default_profile_id ?? null;
  const rows = teamModelRows(profiles, [effectiveDefault]);
  const defaultRow = rowForProfile(rows, profiles, effectiveDefault);
  const disabled = policy?.disabled_model_ids ?? [];
  const reasoningOff = policy?.reasoning_default_off_model_ids ?? [];
  // A write while a read is in flight would be built on stale lists.
  const locked = !canWrite || isSaving || isFetchingPolicy || isFetchingModels;

  const persist = async (patch: UpdateTeamRoutingPolicyRequest) => {
    setError(null);
    try {
      await updateRoutingPolicy({
        teamId: team.id,
        updateTeamRoutingPolicyRequest: {
          chat_default_profile_id: storedDefault,
          disabled_model_ids: disabled,
          reasoning_default_off_model_ids: reasoningOff,
          expected_version: policy?.version ?? 0,
          ...patch,
        },
      }).unwrap();
    } catch (err) {
      const normalized = normalizeApiError(err);
      if (normalized.kind === "conflict") {
        // Someone else saved meanwhile: show their version rather than overwrite it.
        void refetchPolicy();
        showWarn({
          summary: t("rework.teamSettings.routing.conflict"),
          detail: t("rework.teamSettings.routing.conflictHint"),
        });
        return;
      }
      setError(normalized.detail ?? t("rework.teamSettings.routing.saveError"));
    }
  };

  const toggleEnabled = async (row: TeamModelRow, enabled: boolean) => {
    if (enabled) {
      await persist({ disabled_model_ids: disabled.filter((id) => id !== row.capabilityId) });
      return;
    }
    // Nothing is written until the admin has seen which agents fall back.
    setPendingDisable({ row });
    try {
      const impact = await fetchDisableImpact({ teamId: team.id, capabilityId: row.capabilityId }, false).unwrap();
      setPendingDisable((current) => (current?.row === row ? { row, impact } : current));
    } catch {
      setPendingDisable((current) => (current?.row === row ? { row, failed: true } : current));
    }
  };

  const confirmDisable = async () => {
    // Not before the impact is known: the admin confirms what they were shown.
    if (!pendingDisable || (!pendingDisable.impact && !pendingDisable.failed)) return;
    const { row } = pendingDisable;
    setPendingDisable(null);
    await persist({ disabled_model_ids: [...disabled, row.capabilityId] });
  };

  const toggleReasoningDefault = (row: TeamModelRow, on: boolean) =>
    persist({
      reasoning_default_off_model_ids: on
        ? reasoningOff.filter((id) => id !== row.capabilityId)
        : [...reasoningOff, row.capabilityId],
    });

  // A default no longer served keeps failing turns until a new one is picked: say so.
  // Its model is then absent from `available-models`, so there is no label to name it by.
  const defaultUnavailable = storedDefault !== null && !defaultRow;
  const impactAgents = pendingDisable?.impact?.agents ?? [];

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.teamSettings.routing.title")} subtitle={t("rework.teamSettings.routing.subtitle")} />

      {!canWrite && <p className={styles.hint}>{t("rework.teamSettings.routing.readOnly")}</p>}

      {defaultUnavailable && (
        <p className={styles.error} role="alert">
          {t("rework.teamSettings.routing.defaultUnavailable")}
        </p>
      )}

      {rows.length === 0 ? (
        <p className={styles.hint}>{t("rework.teamSettings.routing.emptyState")}</p>
      ) : (
        <ul className={styles.models}>
          {rows.map((row) => {
            const isDefault = row === defaultRow;
            const isEnabled = !disabled.includes(row.capabilityId);
            const helperId = `team-models-default-${row.capabilityId}`;
            const enableSwitch = (
              <Switch
                size="small"
                checked={isEnabled}
                disabled={locked || isDefault}
                onChange={(event) => void toggleEnabled(row, event.target.checked)}
                aria-label={t("rework.teamSettings.routing.enabledLabel", { model: row.label })}
                aria-describedby={isDefault ? helperId : undefined}
              />
            );
            return (
              <li key={row.capabilityId} className={styles.tile} data-disabled={!isEnabled || undefined}>
                {isDefault ? (
                  <span className={styles.toggle}>{enableSwitch}</span>
                ) : (
                  <Tooltip text={t("rework.teamSettings.routing.enabledTooltip")}>
                    <span className={styles.toggle}>{enableSwitch}</span>
                  </Tooltip>
                )}
                <span className={styles.label}>
                  <span className={styles.name} title={row.label}>
                    {row.label}
                  </span>
                  {/* Visible, not a tooltip: the switch it explains is disabled. */}
                  {isDefault && (
                    <span id={helperId} className={styles.hint}>
                      {t("rework.teamSettings.routing.defaultCannotBeDisabled")}
                    </span>
                  )}
                </span>
                {row.reasoningAvailable && (
                  <span className={styles.reasoning}>
                    <span aria-hidden="true">{t("rework.teamSettings.routing.reasoningDefault")}</span>
                    <Switch
                      size="small"
                      checked={!reasoningOff.includes(row.capabilityId)}
                      disabled={locked || !isEnabled}
                      onChange={(event) => void toggleReasoningDefault(row, event.target.checked)}
                      aria-label={t("rework.teamSettings.routing.reasoningDefaultLabel", { model: row.label })}
                    />
                  </span>
                )}
                <Button
                  color="primary"
                  variant={isDefault ? "text" : "outlined"}
                  size="small"
                  icon={isDefault ? { category: "outlined", type: "check", filled: false } : undefined}
                  disabled={locked || isDefault || !isEnabled}
                  onClick={() => void persist({ chat_default_profile_id: row.profileId })}
                >
                  {isDefault ? t("rework.teamSettings.routing.isDefault") : t("rework.teamSettings.routing.setDefault")}
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <ConfirmationDialog
        open={pendingDisable !== null}
        title={t("rework.teamSettings.routing.disableDialog.title", { model: pendingDisable?.row.label ?? "" })}
        confirmLabel={t("rework.teamSettings.routing.disableDialog.confirm")}
        cancelLabel={t("common.cancel")}
        criticalAction
        onConfirm={() => void confirmDisable()}
        onCancel={() => setPendingDisable(null)}
        details={
          <div className={styles.dialogBody}>
            {pendingDisable?.failed ? (
              <p className={styles.error}>{t("rework.teamSettings.routing.disableDialog.loadError")}</p>
            ) : !pendingDisable?.impact ? (
              <p>{t("rework.teamSettings.routing.disableDialog.loading")}</p>
            ) : impactAgents.length === 0 ? (
              <p>{t("rework.teamSettings.routing.disableDialog.noAgents")}</p>
            ) : (
              <>
                <p>
                  {defaultRow
                    ? t("rework.teamSettings.routing.disableDialog.agents", { model: defaultRow.label })
                    : t("rework.teamSettings.routing.disableDialog.agentsUnnamed")}
                </p>
                <ul className={styles.agents}>
                  {impactAgents.map((agent) => (
                    <li key={agent.agent_instance_id}>{agent.display_name}</li>
                  ))}
                </ul>
              </>
            )}
            <p>
              {defaultRow
                ? t("rework.teamSettings.routing.disableDialog.conversations", { model: defaultRow.label })
                : t("rework.teamSettings.routing.disableDialog.conversationsUnnamed")}
            </p>
          </div>
        }
      />
    </div>
  );
}
