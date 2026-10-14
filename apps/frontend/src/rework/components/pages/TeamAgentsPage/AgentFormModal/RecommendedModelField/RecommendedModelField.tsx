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

import { useTranslation } from "react-i18next";
import Select, { type SelectOption } from "@shared/molecules/Select/Select.tsx";
import { rowForProfile, teamModelRows } from "@rework/features/capabilities/teamModelRows";
import {
  useAvailableModelProfilesQuery,
  useTeamRoutingPolicyQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./RecommendedModelField.module.css";

const TEAM_DEFAULT = "";

interface RecommendedModelFieldProps {
  teamId?: string;
  /** Stored chat profile id; null follows the team default. */
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
}

/**
 * The agent's recommended model: the team default (stored as null, so it tracks
 * later default changes) or one specific team-enabled model, pinned even if it is
 * today's default. A stored value no longer offered stays shown, flagged.
 */
export function RecommendedModelField({ teamId, value, onChange, disabled }: RecommendedModelFieldProps) {
  const { t } = useTranslation();
  const skip = !teamId;
  const { data: policy } = useTeamRoutingPolicyQuery({ teamId: teamId ?? "" }, { skip });
  const { data: availableModels } = useAvailableModelProfilesQuery({ teamId: teamId ?? "" }, { skip });

  const profiles = availableModels?.profiles ?? [];
  if (profiles.length === 0 && !value) return null;

  const effectiveDefault = policy?.chat_default_profile_id ?? availableModels?.effective_default_profile_id ?? null;
  // The stored value keys its model's row, so a sibling profile of the default never adds a row.
  const allRows = teamModelRows(profiles, [value, effectiveDefault]);
  const defaultLabel = rowForProfile(allRows, profiles, effectiveDefault)?.label;
  const disabledIds = new Set(policy?.disabled_model_ids ?? []);
  const rows = allRows.filter((row) => !disabledIds.has(row.capabilityId));
  const stale = value !== null && !rows.some((row) => row.profileId === value);
  const staleLabel = allRows.find((row) => row.profileId === value)?.label ?? value;

  const options: SelectOption<string>[] = [
    {
      value: TEAM_DEFAULT,
      key: "__team_default__",
      label: t("rework.teams.formAgent.fields.recommendedModel.teamDefault"),
      description: defaultLabel
        ? t("rework.teams.formAgent.fields.recommendedModel.teamDefaultCurrent", { model: defaultLabel })
        : t("rework.teams.formAgent.fields.recommendedModel.teamDefaultFollows"),
    },
    ...rows.map((row) => ({ value: row.profileId, key: row.profileId, label: row.label })),
    ...(stale && value
      ? [
          {
            value,
            key: value,
            label: staleLabel ?? value,
            description: t("rework.teams.formAgent.fields.recommendedModel.unavailableOption"),
          },
        ]
      : []),
  ];

  return (
    <div className={styles.field}>
      <Select
        size="medium"
        label={t("rework.teams.formAgent.fields.recommendedModel.label")}
        value={value ?? TEAM_DEFAULT}
        options={options}
        onChange={(next) => onChange(next === TEAM_DEFAULT ? null : next)}
        disabled={disabled}
        error={
          stale ? t("rework.teams.formAgent.fields.recommendedModel.unavailable", { model: staleLabel }) : undefined
        }
      />
      <p className={styles.hint}>{t("rework.teams.formAgent.fields.recommendedModel.hint")}</p>
    </div>
  );
}
