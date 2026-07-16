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

// Per-capability team matrix (CAPAB-01 / #1981, RFC §8.5). One row per team with
// its tri-state and the enable-with-settings / disable actions. The enable form
// is rendered from the capability's `team_settings_fields` through the shared
// metadata-driven `TuningFieldRenderer` — no bespoke UI for scalar settings.

import Button from "@shared/atoms/Button/Button.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import SearchField from "@shared/molecules/SearchField/SearchField.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type {
  CapabilityEnablementItem,
  ManagedAgentFieldSpec,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useDisableTeamCapabilityMutation,
  useEnableTeamCapabilityMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { TuningFieldRenderer } from "../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer.tsx";
import styles from "./CapabilityTeamMatrixDrawer.module.css";
import {
  filterTeamsByName,
  seedSettingsFromFields,
  teamCapabilityState,
  type TeamCapabilityState,
} from "./capabilityEnablement";

interface CapabilityTeamMatrixDrawerProps {
  capability: CapabilityEnablementItem | null;
  teams: Team[];
  open: boolean;
  onClose: () => void;
  /** Bubble up the count of instances a revoke suspended, for the health column. */
  onSuspended: (capabilityId: string, count: number) => void;
}

const STATE_LABEL_KEY: Record<TeamCapabilityState, string> = {
  enabled: "rework.admin.capabilities.matrix.state.enabled",
  inherited: "rework.admin.capabilities.matrix.state.inherited",
  off: "rework.admin.capabilities.matrix.state.off",
};

export function CapabilityTeamMatrixDrawer({
  capability,
  teams,
  open,
  onClose,
  onSuspended,
}: CapabilityTeamMatrixDrawerProps) {
  const { t } = useTranslation();
  const { showSuccess, showError, showWarn } = useToast();
  const [enableCapability, { isLoading: isEnabling }] = useEnableTeamCapabilityMutation();
  const [disableCapability, { isLoading: isDisabling }] = useDisableTeamCapabilityMutation();

  // The team currently being configured with an enable-with-settings form.
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [teamQuery, setTeamQuery] = useState("");

  // The drawer component stays mounted across open/close, so stale queries
  // from a previous capability would silently pre-filter the next one.
  useEffect(() => {
    setTeamQuery("");
  }, [capability?.id]);

  const busy = isEnabling || isDisabling;
  const fields = capability?.team_settings_fields ?? [];
  const hasSettings = fields.length > 0;

  const hasQuery = teamQuery.trim() !== "";
  const visibleTeams = filterTeamsByName(teams, teamQuery);

  const startEnable = (teamId: string) => {
    if (!capability) return;
    if (hasSettings) {
      setEditingTeamId(teamId);
      setFormValues(seedSettingsFromFields(fields));
    } else {
      void submitEnable(teamId, {});
    }
  };

  const submitEnable = async (teamId: string, settings: Record<string, unknown>) => {
    if (!capability) return;
    try {
      await enableCapability({
        capabilityId: capability.id,
        teamId,
        enableTeamCapabilityRequest: { settings },
      }).unwrap();
      showSuccess({ summary: t("rework.admin.capabilities.matrix.enabledToast", { team: teamId }) });
      setEditingTeamId(null);
    } catch {
      showError({ summary: t("rework.admin.capabilities.matrix.enableError") });
    }
  };

  const submitDisable = async (teamId: string) => {
    if (!capability) return;
    try {
      const result = await disableCapability({ capabilityId: capability.id, teamId }).unwrap();
      const suspended = result.suspended_instances ?? 0;
      onSuspended(capability.id, suspended);
      if (suspended > 0) {
        showWarn({
          summary: t("rework.admin.capabilities.matrix.disabledSuspendedToast", {
            team: teamId,
            count: suspended,
          }),
        });
      } else {
        showSuccess({ summary: t("rework.admin.capabilities.matrix.disabledToast", { team: teamId }) });
      }
    } catch {
      showError({ summary: t("rework.admin.capabilities.matrix.disableError") });
    }
  };

  const title = capability
    ? t("rework.admin.capabilities.matrix.title", { name: t(capability.name, { defaultValue: capability.name }) })
    : "";

  return (
    <InlineDrawer open={open} onClose={onClose} title={title} width="520px">
      {capability && (
        <div className={styles.body}>
          <p className={styles.hint}>{t("rework.admin.capabilities.matrix.subtitle")}</p>
          <SearchField
            value={teamQuery}
            onChange={setTeamQuery}
            placeholder={t("rework.admin.capabilities.matrix.searchPlaceholder")}
            clearAriaLabel={t("rework.admin.capabilities.matrix.clearSearch")}
            autoFocus
          />
          {hasQuery && visibleTeams.length === 0 && (
            <p className={styles.hint}>{t("rework.admin.capabilities.matrix.searchEmpty")}</p>
          )}
          <ul className={styles.teamList}>
            {visibleTeams.map((team) => {
              const state = teamCapabilityState(capability, team.id);
              const on = state !== "off";
              const isEditing = editingTeamId === team.id;
              return (
                <li key={team.id} className={styles.teamRow}>
                  <div className={styles.teamMain}>
                    <span className={styles.teamName}>{team.name}</span>
                    <span className={styles.stateBadge} data-state={state}>
                      {t(STATE_LABEL_KEY[state])}
                    </span>
                  </div>
                  <div className={styles.teamActions}>
                    {on ? (
                      <Button
                        color="on-surface"
                        variant="outlined"
                        size="small"
                        disabled={busy}
                        onClick={() => submitDisable(team.id)}
                      >
                        {t("rework.admin.capabilities.matrix.disable")}
                      </Button>
                    ) : (
                      <Button
                        color="primary"
                        variant="outlined"
                        size="small"
                        disabled={busy || isEditing}
                        onClick={() => startEnable(team.id)}
                      >
                        {t("rework.admin.capabilities.matrix.enable")}
                      </Button>
                    )}
                  </div>
                  {isEditing && (
                    <form
                      className={styles.settingsForm}
                      onSubmit={(e) => {
                        e.preventDefault();
                        void submitEnable(team.id, formValues);
                      }}
                    >
                      {fields.map((field) => (
                        <TuningFieldRenderer
                          key={field.key}
                          field={field as ManagedAgentFieldSpec}
                          value={formValues[field.key]}
                          onChange={(key, value) => setFormValues((prev) => ({ ...prev, [key]: value }))}
                          disabled={busy}
                        />
                      ))}
                      <div className={styles.settingsActions}>
                        <Button color="on-surface" variant="text" size="small" onClick={() => setEditingTeamId(null)}>
                          {t("rework.admin.capabilities.matrix.cancel")}
                        </Button>
                        <Button color="primary" variant="filled" size="small" type="submit" disabled={busy}>
                          {t("rework.admin.capabilities.matrix.saveEnable")}
                        </Button>
                      </div>
                    </form>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </InlineDrawer>
  );
}
