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
import {
  useAvailableModelProfilesQuery,
  useTeamRoutingPolicyQuery,
  useUpdateTeamRoutingPolicyMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";

const NO_DEFAULT = "";

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
function newRow(): RuleRow {
  nextKey += 1;
  return { key: `new-${nextKey}`, rule_id: "", operation: "", purpose: null, target_profile_id: "" };
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
    const options: OptionModel<string>[] = (availableModels?.profiles ?? []).map((profile) => ({
      value: profile.profile_id,
      label: `${t(profile.name, { defaultValue: profile.name })} (${profile.profile_id})`,
      key: profile.profile_id,
    }));
    const known = new Set(options.map((option) => option.value));
    const stale = new Set<string>();
    if (chatDefaultProfileId && !known.has(chatDefaultProfileId)) stale.add(chatDefaultProfileId);
    rows.forEach((row) => {
      if (row.target_profile_id && !known.has(row.target_profile_id)) stale.add(row.target_profile_id);
    });
    stale.forEach((profileId) =>
      options.push({
        value: profileId,
        label: profileId,
        key: profileId,
        description: t("rework.teamSettings.routing.profileUnavailable"),
      }),
    );
    return options;
  }, [availableModels, chatDefaultProfileId, rows, t]);

  if (isLoading || isLoadingModels) return null;

  const hasNoModelsAvailable = profileOptions.length === 0;

  const handleAddRow = () => setRows((prev) => [...prev, newRow()]);
  const handleRemoveRow = (key: string) => setRows((prev) => prev.filter((r) => r.key !== key));
  const handleRowChange = (key: string, field: "operation" | "purpose", value: string) => {
    setRows((prev) =>
      prev.map((r) => (r.key === key ? { ...r, [field]: field === "purpose" && value === "" ? null : value } : r)),
    );
  };
  const handleRowProfileChange = (key: string, targetProfileId: string) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, target_profile_id: targetProfileId } : r)));
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
      const detail =
        err &&
        typeof err === "object" &&
        "data" in err &&
        err.data &&
        typeof err.data === "object" &&
        "detail" in err.data
          ? String((err.data as { detail: unknown }).detail)
          : t("rework.teamSettings.routing.saveError");
      setError(detail);
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
                label={t("rework.teamSettings.routing.operationRules.operation")}
                value={row.operation}
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
