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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import styles from "./TeamSettingsRouting.module.scss";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import type { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAvailableModelProfilesQuery,
  useTeamRoutingPolicyQuery,
  useUpdateTeamRoutingPolicyMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";

const NO_DEFAULT = "";
const NO_AGENT = "";

interface TeamSettingsRoutingProps {
  team: TeamWithPermissions;
  /** Read-only for team_admin — team_editor writes, team_admin reads. */
  canWrite: boolean;
}

/** Local editing shape — a stable client-side key so React can track rows
 * across add/remove, distinct from the `agent_id` the row currently holds
 * (empty until an agent is picked). */
interface OverrideRow {
  key: string;
  agentId: string;
  targetProfileId: string;
}

let nextKey = 0;
function newRow(): OverrideRow {
  nextKey += 1;
  return { key: `new-${nextKey}`, agentId: NO_AGENT, targetProfileId: "" };
}

/** Build a picker's option list from a base catalog, keeping any row's
 * currently-referenced value selectable even if the catalog no longer lists
 * it (renamed/removed upstream) — flagged via description rather than
 * silently dropped. Shared by the profile and agent pickers below, which
 * differ only in their catalog shape and current-value source. */
function withUnavailableFallback(
  base: OptionModel<string>[],
  currentValues: Iterable<string | null | undefined>,
  unavailableLabel: string,
): OptionModel<string>[] {
  const known = new Set(base.map((option) => option.value));
  const stale = new Set<string>();
  for (const value of currentValues) {
    if (value && !known.has(value)) stale.add(value);
  }
  if (stale.size === 0) return base;
  const options = [...base];
  stale.forEach((value) => options.push({ value, label: value, key: value, description: unavailableLabel }));
  return options;
}

/**
 * Team-owned LLM model routing policy. One default chat profile plus zero or
 * more per-agent overrides (`agent_id -> profile_id`). Both profile pickers
 * are scoped to the team's `kind="model"` capability enablement
 * (`available-models`) — a stale reference (e.g. a capability disabled after
 * the policy was written) still surfaces as a selectable option rather than
 * silently disappearing, flagged via its option description.
 */
export default function TeamSettingsRouting({ team, canWrite }: TeamSettingsRoutingProps) {
  const { t } = useTranslation();
  const { data: policy, isLoading } = useTeamRoutingPolicyQuery({ teamId: team.id });
  const { data: availableModels, isLoading: isLoadingModels } = useAvailableModelProfilesQuery({
    teamId: team.id,
  });
  // The team's agents — for the per-row agent override. The row's `agentId`
  // matches the runtime's `definition.agent_id`, i.e. the template's
  // `source_agent_id`.
  const { data: agentTemplates } = useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery({
    teamId: team.id,
  });
  const [updateRoutingPolicy, { isLoading: isSaving }] = useUpdateTeamRoutingPolicyMutation();

  const [chatDefaultProfileId, setChatDefaultProfileId] = useState(NO_DEFAULT);
  const [rows, setRows] = useState<OverrideRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!policy) return;
    setChatDefaultProfileId(policy.chat_default_profile_id ?? NO_DEFAULT);
    setRows(
      Object.entries(policy.agent_profile_overrides ?? {}).map(([agentId, targetProfileId]) => ({
        key: agentId,
        agentId,
        targetProfileId,
      })),
    );
  }, [policy]);

  const profileOptions: OptionModel<string>[] = useMemo(() => {
    const base: OptionModel<string>[] = (availableModels?.profiles ?? []).map((profile) => ({
      value: profile.profile_id,
      label: `${t(profile.name, { defaultValue: profile.name })} (${profile.profile_id})`,
      key: profile.profile_id,
    }));
    const currentValues = [chatDefaultProfileId, ...rows.map((row) => row.targetProfileId)];
    return withUnavailableFallback(base, currentValues, t("rework.teamSettings.routing.profileUnavailable"));
  }, [availableModels, chatDefaultProfileId, rows, t]);

  const allAgentOptions: OptionModel<string>[] = useMemo(() => {
    const base: OptionModel<string>[] = [];
    const seenTemplateIds = new Set<string>();
    (agentTemplates ?? []).forEach((tpl) => {
      if (seenTemplateIds.has(tpl.source_agent_id)) return;
      seenTemplateIds.add(tpl.source_agent_id);
      base.push({ value: tpl.source_agent_id, label: tpl.display_name, key: tpl.source_agent_id });
    });
    return withUnavailableFallback(
      base,
      rows.map((row) => row.agentId),
      t("rework.teamSettings.routing.profileUnavailable"),
    );
  }, [agentTemplates, rows, t]);

  if (isLoading || isLoadingModels) return null;

  const hasNoModelsAvailable = profileOptions.length === 0;

  const handleAddRow = () => setRows((prev) => [...prev, newRow()]);
  const handleRemoveRow = (key: string) => setRows((prev) => prev.filter((r) => r.key !== key));
  const handleRowProfileChange = (key: string, targetProfileId: string) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, targetProfileId } : r)));
  };
  const handleRowAgentChange = (key: string, agentId: string) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, agentId } : r)));
  };

  const handleSave = async () => {
    setError(null);
    // A row with only one of the two fields picked is not silently dropped —
    // that would report success while discarding the edit the user is
    // clearly still mid-way through.
    const hasIncompleteRow = rows.some((row) => Boolean(row.agentId) !== Boolean(row.targetProfileId));
    if (hasIncompleteRow) {
      setError(t("rework.teamSettings.routing.agentOverrides.incompleteRow"));
      return;
    }
    try {
      const agentProfileOverrides = Object.fromEntries(
        rows.filter((row) => row.agentId && row.targetProfileId).map((row) => [row.agentId, row.targetProfileId]),
      );
      await updateRoutingPolicy({
        teamId: team.id,
        updateTeamRoutingPolicyRequest: {
          chat_default_profile_id: chatDefaultProfileId || null,
          agent_profile_overrides: agentProfileOverrides,
        },
      }).unwrap();
    } catch (err) {
      setError(normalizeApiError(err).detail ?? t("rework.teamSettings.routing.saveError"));
    }
  };

  return (
    <div className={styles["team-settings-routing-container"]}>
      <PageHeader title={t("rework.teamSettings.routing.title")} />
      <div className={styles["form-section"]}>
        <span className={styles["section-title"]}>{t("rework.teamSettings.routing.defaultProfile.title")}</span>
        <span className={styles["section-explanation"]}>
          {t("rework.teamSettings.routing.defaultProfile.explanation")}
        </span>
        {hasNoModelsAvailable ? (
          <span className={styles["section-explanation"]}>{t("rework.teamSettings.routing.emptyState")}</span>
        ) : (
          <Select
            size="medium"
            label={t("rework.teamSettings.routing.defaultProfile.label")}
            value={chatDefaultProfileId}
            options={[
              {
                value: NO_DEFAULT,
                label: t("rework.teamSettings.routing.defaultProfile.useDeploymentDefault"),
                key: "__no_default__",
              },
              ...profileOptions,
            ]}
            onChange={setChatDefaultProfileId}
            disabled={!canWrite}
          />
        )}
      </div>

      {!hasNoModelsAvailable && (
        <div className={styles["form-section"]}>
          <span className={styles["section-title"]}>{t("rework.teamSettings.routing.agentOverrides.title")}</span>
          <span className={styles["section-explanation"]}>
            {t("rework.teamSettings.routing.agentOverrides.explanation")}
          </span>
          {rows.map((row) => {
            // Exclude agents already picked by another row so two rows can
            // never silently collapse onto the same agent_id key on save.
            const agentOptions = allAgentOptions.filter(
              (option) =>
                option.value === row.agentId || !rows.some((r) => r.key !== row.key && r.agentId === option.value),
            );
            return (
              <div className={styles["rule-row"]} key={row.key}>
                <Select
                  size="medium"
                  label={t("rework.teamSettings.routing.agentOverrides.agent")}
                  placeholder={t("rework.teamSettings.routing.agentOverrides.agentPlaceholder")}
                  value={row.agentId}
                  options={agentOptions}
                  onChange={(value) => handleRowAgentChange(row.key, value)}
                  disabled={!canWrite}
                />
                <Select
                  size="medium"
                  label={t("rework.teamSettings.routing.agentOverrides.targetProfileId")}
                  placeholder={t("rework.teamSettings.routing.agentOverrides.targetProfilePlaceholder")}
                  value={row.targetProfileId}
                  options={profileOptions}
                  onChange={(value) => handleRowProfileChange(row.key, value)}
                  disabled={!canWrite}
                />
                {canWrite && <DeleteIconButton onClick={() => handleRemoveRow(row.key)} />}
              </div>
            );
          })}
          {canWrite && (
            <Button color="secondary" variant="outlined" size="small" onClick={handleAddRow}>
              {t("rework.teamSettings.routing.agentOverrides.addRule")}
            </Button>
          )}
        </div>
      )}

      {canWrite && !hasNoModelsAvailable && (
        <div className={styles["actions-row"]}>
          <Button color="primary" variant="filled" size="medium" onClick={handleSave} disabled={isSaving}>
            {t("rework.teamSettings.routing.save")}
          </Button>
          {error && <span className={styles["error-message"]}>{error}</span>}
        </div>
      )}
    </div>
  );
}
