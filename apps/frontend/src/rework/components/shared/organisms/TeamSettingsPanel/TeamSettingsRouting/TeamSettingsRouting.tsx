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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./TeamSettingsRouting.module.scss";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import type {
  TeamOperationRouteRule,
  TeamWithPermissions,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useTeamRoutingPolicyQuery,
  useUpdateTeamRoutingPolicyMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";

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
 * per-operation overrides, both free-text profile ids validated server-side
 * against the team's `kind="model"` capability enablement (§7) — the server
 * response's 400 detail is the source of truth for "not allowed", surfaced
 * inline rather than pre-filtered client-side (no team-facing "list my
 * enabled models" endpoint exists yet; the admin capabilities matrix is
 * platform-admin-only and cannot back a picker here).
 */
export default function TeamSettingsRouting({ team, canWrite }: TeamSettingsRoutingProps) {
  const { t } = useTranslation();
  const { data: policy, isLoading } = useTeamRoutingPolicyQuery({ teamId: team.id });
  const [updateRoutingPolicy, { isLoading: isSaving }] = useUpdateTeamRoutingPolicyMutation();

  const [chatDefaultProfileId, setChatDefaultProfileId] = useState("");
  const [rows, setRows] = useState<RuleRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!policy) return;
    setChatDefaultProfileId(policy.chat_default_profile_id ?? "");
    setRows((policy.operation_rules ?? []).map((rule) => ({ ...rule, key: rule.rule_id })));
  }, [policy]);

  if (isLoading) return null;

  const handleAddRow = () => setRows((prev) => [...prev, newRow()]);
  const handleRemoveRow = (key: string) => setRows((prev) => prev.filter((r) => r.key !== key));
  const handleRowChange = (key: string, field: keyof TeamOperationRouteRule, value: string) => {
    setRows((prev) =>
      prev.map((r) => (r.key === key ? { ...r, [field]: field === "purpose" && value === "" ? null : value } : r)),
    );
  };

  const handleSave = async () => {
    setError(null);
    try {
      await updateRoutingPolicy({
        teamId: team.id,
        updateTeamRoutingPolicyRequest: {
          chat_default_profile_id: chatDefaultProfileId.trim() || null,
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
      <div className={styles["form-section"]}>
        <span className={styles["section-title"]}>{t("rework.teamSettings.routing.defaultProfile.title")}</span>
        <span className={styles["section-explanation"]}>
          {t("rework.teamSettings.routing.defaultProfile.explanation")}
        </span>
        <TextInput
          label={t("rework.teamSettings.routing.defaultProfile.label")}
          placeholder={t("rework.teamSettings.routing.defaultProfile.placeholder")}
          value={chatDefaultProfileId}
          onChange={(e) => setChatDefaultProfileId(e.target.value)}
          disabled={!canWrite}
        />
      </div>

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
            <TextInput
              label={t("rework.teamSettings.routing.operationRules.targetProfileId")}
              value={row.target_profile_id}
              onChange={(e) => handleRowChange(row.key, "target_profile_id", e.target.value)}
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

      {canWrite && (
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
