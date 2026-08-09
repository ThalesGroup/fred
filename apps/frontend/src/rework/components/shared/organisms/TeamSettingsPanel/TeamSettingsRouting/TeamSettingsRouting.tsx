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
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import type {
  TeamOperationRouteRule,
  TeamWithPermissions,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAvailableModelProfilesQuery,
  useTeamRoutingPolicyQuery,
  useUpdateTeamRoutingPolicyMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";

const NO_DEFAULT = "";
// Sentinel for the "applies to every agent" option (rule.agent_id = null).
const AGENT_ANY = "";

interface TeamSettingsRoutingProps {
  team: TeamWithPermissions;
  /** Read-only for team_admin (RFC §6/§13) — team_editor writes, team_admin reads. */
  canWrite: boolean;
}

/** Local editing shape — a stable client-side key so React can track rows
 * across add/remove before a rule_id is chosen, distinct from the field the
 * server actually validates. */
interface RuleRow extends TeamOperationRouteRule {
  key: string;
}

let nextKey = 0;
/** `defaultAgentId` should be the team's first real agent, when it has one —
 * a row with both `operation` and `agent_id` null always fails write-time
 * validation (`validate_at_least_one_criterion`) and free-text `operation`
 * has no meaningful non-null default, so `agent_id` is the only field that
 * can start non-null and still mean something (this PR's whole point is
 * per-agent overrides). Falls back to null (today's "any agent") only when
 * the team has no agents to pick from yet. */
function newRow(defaultAgentId: string | null): RuleRow {
  nextKey += 1;
  // `rule_id` is a server-required, non-empty stable identifier
  // (`TeamOperationRouteRule.rule_id`, min_length=1). The form never surfaces
  // it, so generate one at creation — without this a new override always failed
  // write-time validation with a 422. Existing rows keep their own rule_id.
  return {
    key: `new-${nextKey}`,
    rule_id: crypto.randomUUID(),
    operation: null,
    purpose: null,
    agent_id: defaultAgentId,
    target_profile_id: "",
  };
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
 * Team-owned LLM model routing policy (TEAM-05, #2118,
 * `TEAM-ROUTING-POLICY-RFC.md`). One default chat profile plus zero or more
 * per-operation overrides. Both profile pickers are scoped to the team's
 * `kind="model"` capability enablement (§7 / §13, `available-models`, #2167)
 * — a stale reference (e.g. a capability disabled after the policy was
 * written) still surfaces as a selectable option rather than silently
 * disappearing, flagged via its option description.
 */
export default function TeamSettingsRouting({ team, canWrite }: TeamSettingsRoutingProps) {
  const { t } = useTranslation();
  const { data: policy, isLoading } = useTeamRoutingPolicyQuery({ teamId: team.id });
  const { data: availableModels, isLoading: isLoadingModels } = useAvailableModelProfilesQuery({
    teamId: team.id,
  });
  // The team's agents — for the optional per-rule agent scope. The rule's
  // `agent_id` matches the runtime's `definition.agent_id`, i.e. the template's
  // `source_agent_id`.
  const { data: agentTemplates } = useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery({
    teamId: team.id,
  });
  const [updateRoutingPolicy, { isLoading: isSaving }] = useUpdateTeamRoutingPolicyMutation();

  const [chatDefaultProfileId, setChatDefaultProfileId] = useState(NO_DEFAULT);
  const [rows, setRows] = useState<RuleRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!policy) return;
    setChatDefaultProfileId(policy.chat_default_profile_id ?? NO_DEFAULT);
    setRows((policy.operation_rules ?? []).map((rule) => ({ ...rule, key: rule.rule_id })));
  }, [policy]);

  const profileOptions: OptionModel<string>[] = useMemo(() => {
    const base: OptionModel<string>[] = (availableModels?.profiles ?? []).map((profile) => ({
      value: profile.profile_id,
      label: `${t(profile.name, { defaultValue: profile.name })} (${profile.profile_id})`,
      key: profile.profile_id,
    }));
    const currentValues = [chatDefaultProfileId, ...rows.map((row) => row.target_profile_id)];
    return withUnavailableFallback(base, currentValues, t("rework.teamSettings.routing.profileUnavailable"));
  }, [availableModels, chatDefaultProfileId, rows, t]);

  const agentOptions: OptionModel<string>[] = useMemo(() => {
    const base: OptionModel<string>[] = [
      { value: AGENT_ANY, label: t("rework.teamSettings.routing.operationRules.agentAny"), key: "__any_agent__" },
    ];
    const seenTemplateIds = new Set<string>([AGENT_ANY]);
    (agentTemplates ?? []).forEach((tpl) => {
      if (seenTemplateIds.has(tpl.source_agent_id)) return;
      seenTemplateIds.add(tpl.source_agent_id);
      base.push({ value: tpl.source_agent_id, label: tpl.display_name, key: tpl.source_agent_id });
    });
    return withUnavailableFallback(
      base,
      rows.map((row) => row.agent_id),
      t("rework.teamSettings.routing.profileUnavailable"),
    );
  }, [agentTemplates, rows, t]);

  if (isLoading || isLoadingModels) return null;

  const hasNoModelsAvailable = profileOptions.length === 0;

  const handleAddRow = () =>
    setRows((prev) => [...prev, newRow(agentTemplates?.[0]?.source_agent_id ?? null)]);
  const handleRemoveRow = (key: string) => setRows((prev) => prev.filter((r) => r.key !== key));
  const handleRowChange = (key: string, field: "operation" | "purpose", value: string) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, [field]: value === "" ? null : value } : r)));
  };
  const handleRowProfileChange = (key: string, targetProfileId: string) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, target_profile_id: targetProfileId } : r)));
  };
  const handleRowAgentChange = (key: string, agentId: string) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, agent_id: agentId || null } : r)));
  };

  const handleSave = async () => {
    setError(null);
    try {
      await updateRoutingPolicy({
        teamId: team.id,
        updateTeamRoutingPolicyRequest: {
          chat_default_profile_id: chatDefaultProfileId || null,
          operation_rules: rows.map(({ key, ...rule }) => {
            void key;
            return rule;
          }),
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
          <span className={styles["section-title"]}>{t("rework.teamSettings.routing.operationRules.title")}</span>
          <span className={styles["section-explanation"]}>
            {t("rework.teamSettings.routing.operationRules.explanation")}
          </span>
          {rows.map((row) => (
            <div className={styles["rule-row"]} key={row.key}>
              <TextInput
                label={`${t("rework.teamSettings.routing.operationRules.operation")} (optional)`}
                value={row.operation ?? ""}
                onChange={(e) => handleRowChange(row.key, "operation", e.target.value)}
                disabled={!canWrite}
              />
              <TextInput
                label={t("rework.teamSettings.routing.operationRules.purpose")}
                value={row.purpose ?? ""}
                onChange={(e) => handleRowChange(row.key, "purpose", e.target.value)}
                disabled={!canWrite}
              />
              <Select
                size="medium"
                label={t("rework.teamSettings.routing.operationRules.agent")}
                value={row.agent_id ?? AGENT_ANY}
                options={agentOptions}
                onChange={(value) => handleRowAgentChange(row.key, value)}
                disabled={!canWrite}
              />
              <Select
                size="medium"
                label={t("rework.teamSettings.routing.operationRules.targetProfileId")}
                placeholder={t("rework.teamSettings.routing.operationRules.targetProfilePlaceholder")}
                value={row.target_profile_id}
                options={profileOptions}
                onChange={(value) => handleRowProfileChange(row.key, value)}
                disabled={!canWrite}
              />
              {canWrite && <DeleteIconButton onClick={() => handleRemoveRow(row.key)} />}
            </div>
          ))}
          {canWrite && (
            <Button color="secondary" variant="outlined" size="small" onClick={handleAddRow}>
              {t("rework.teamSettings.routing.operationRules.addRule")}
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
