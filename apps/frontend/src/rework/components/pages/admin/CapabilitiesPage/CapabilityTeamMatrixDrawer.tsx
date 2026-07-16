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

// Per-capability team matrix (CAPAB-01 / #1981, RFC §8.5). One row per team
// with a Disable / Default / Enable segmented control over the team's explicit
// position; rows where the capability is effectively off are dimmed, like the
// catalog table. The enable form is rendered from the capability's
// `team_settings_fields` through the shared metadata-driven
// `TuningFieldRenderer` — no bespoke UI for scalar settings.

import Button from "@shared/atoms/Button/Button.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import SearchField from "@shared/molecules/SearchField/SearchField.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type {
  CapabilityEnablementItem,
  ManagedAgentFieldSpec,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useDisableTeamCapabilityMutation,
  useEnableTeamCapabilityMutation,
  useSetCapabilityPersonalScopeMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { TuningFieldRenderer } from "../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer.tsx";
import styles from "./CapabilityTeamMatrixDrawer.module.css";
import {
  PERSONAL_SCOPE_ROW_ID,
  capabilityPersonalScopeChoice,
  excludePersonalTeams,
  filterTeamsByName,
  isCapabilityOnForTeam,
  seedSettingsFromFields,
  sortTeamsForMatrix,
  teamCapabilityChoice,
  type TeamCapabilityChoice,
} from "./capabilityEnablement";

interface CapabilityTeamMatrixDrawerProps {
  capability: CapabilityEnablementItem | null;
  teams: Team[];
  open: boolean;
  onClose: () => void;
  /** Bubble up the count of instances a revoke suspended, for the health column. */
  onSuspended: (capabilityId: string, count: number) => void;
}

/** Segment order of the tri-state control; index ↔ choice for `ButtonGroup`. */
const CHOICES: TeamCapabilityChoice[] = ["disabled", "default", "enabled"];

const CHOICE_LABEL_KEY: Record<TeamCapabilityChoice, string> = {
  disabled: "rework.admin.capabilities.matrix.disable",
  default: "rework.admin.capabilities.matrix.default",
  enabled: "rework.admin.capabilities.matrix.enable",
};

/** Toast keys for the two "team may lose access" mutations (opt-out / reset). */
const OFF_TOAST_KEYS = {
  disable: {
    done: "rework.admin.capabilities.matrix.disabledToast",
    suspended: "rework.admin.capabilities.matrix.disabledSuspendedToast",
    error: "rework.admin.capabilities.matrix.disableError",
  },
  default: {
    done: "rework.admin.capabilities.matrix.defaultToast",
    suspended: "rework.admin.capabilities.matrix.defaultSuspendedToast",
    error: "rework.admin.capabilities.matrix.defaultError",
  },
} as const;

/** Toast keys for the synthetic "All personal spaces" row (RFC §8.4). The
 * "team" placeholder is filled with the localized class label. */
const PERSONAL_TOAST_KEYS = {
  enabled: {
    done: "rework.admin.capabilities.matrix.personal.enabledToast",
    error: "rework.admin.capabilities.matrix.personal.enableError",
  },
  disabled: {
    done: "rework.admin.capabilities.matrix.personal.disabledToast",
    suspended: "rework.admin.capabilities.matrix.personal.disabledSuspendedToast",
    error: "rework.admin.capabilities.matrix.personal.disableError",
  },
  default: {
    done: "rework.admin.capabilities.matrix.personal.defaultToast",
    suspended: "rework.admin.capabilities.matrix.personal.defaultSuspendedToast",
    error: "rework.admin.capabilities.matrix.personal.defaultError",
  },
} as const;

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
  const [setPersonalScope, { isLoading: isSettingPersonal }] = useSetCapabilityPersonalScopeMutation();

  // The team currently being configured with an enable-with-settings form.
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [teamQuery, setTeamQuery] = useState("");

  // In-flight tri-state changes, keyed by team. The segment moves
  // optimistically and a spinner marks the row until the change settles —
  // otherwise the control sits still for the whole mutation + list-refetch
  // round-trip and a click appears to do nothing (except the toast). A map,
  // not a single entry: once a mutation has resolved (busy=false) but its
  // refetch is still in flight, the admin can already start a change on
  // another row, and that must not revert the first row's optimistic state.
  const [pendingByTeam, setPendingByTeam] = useState<Record<string, TeamCapabilityChoice>>({});

  const markPending = (teamId: string, choice: TeamCapabilityChoice) =>
    setPendingByTeam((prev) => ({ ...prev, [teamId]: choice }));
  const unmarkPending = (teamId: string) =>
    setPendingByTeam((prev) => {
      const next = { ...prev };
      delete next[teamId];
      return next;
    });

  // `busy` at settle time, readable from the effect below without making the
  // effect re-run (and wrongly drop entries) on every mutation start/stop.
  const busy = isEnabling || isDisabling || isSettingPersonal;
  const busyRef = useRef(busy);
  busyRef.current = busy;

  // Settle signal: the capability prop is resolved from the live query, so its
  // identity changes exactly when a post-mutation refetch lands. Entries the
  // refetch confirms are dropped (the server's answer takes over the row);
  // while another mutation is still in flight its not-yet-confirmed entry is
  // kept, awaiting its own refetch. Once nothing is in flight everything is
  // cleared — a leftover here means the server diverged from the optimistic
  // choice, and reality must win over a stuck spinner.
  useEffect(() => {
    setPendingByTeam((prev) => {
      if (Object.keys(prev).length === 0) return prev;
      if (!capability || !busyRef.current) return {};
      const next: Record<string, TeamCapabilityChoice> = {};
      for (const [rowId, choice] of Object.entries(prev)) {
        const settled =
          rowId === PERSONAL_SCOPE_ROW_ID
            ? capabilityPersonalScopeChoice(capability)
            : teamCapabilityChoice(capability, rowId);
        if (settled !== choice) {
          next[rowId] = choice;
        }
      }
      return next;
    });
  }, [capability]);

  // Latest capability for the sort snapshot below — a ref, so the effect can
  // read fresh enablement facts without depending on the object identity,
  // which changes on every refetch a tri-state click triggers.
  const capabilityRef = useRef(capability);
  capabilityRef.current = capability;

  // The by-state ordering is a snapshot taken when the drawer opens or targets
  // another capability — NOT re-derived per mutation, which would teleport the
  // row the admin just clicked into another group. The tri-state control and
  // dimming still track live data. `teams` is a dep only because the roster
  // can finish loading after the drawer is already open. The query reset lives
  // in the same effect because the drawer stays mounted across open/close, so
  // a stale query from a previous capability would silently pre-filter the
  // next one.
  // Personal spaces are governed by the synthetic class row (RFC §8.4), so the
  // admin's own personal team is dropped from the ordinary per-team roster.
  const [orderedTeams, setOrderedTeams] = useState<Team[]>(() => excludePersonalTeams(teams));
  useEffect(() => {
    setTeamQuery("");
    const snapshot = capabilityRef.current;
    const roster = excludePersonalTeams(teams);
    setOrderedTeams(snapshot ? sortTeamsForMatrix(roster, snapshot) : roster);
  }, [capability?.id, open, teams]);

  const fields = capability?.team_settings_fields ?? [];
  const hasSettings = fields.length > 0;
  // A capability with a REQUIRED team setting cannot be class-enabled for all
  // personal spaces (nobody filled the settings) — same §8.2 rule as default-on.
  const requiresSettings = fields.some((field) => field.required);

  const hasQuery = teamQuery.trim() !== "";
  const visibleTeams = filterTeamsByName(orderedTeams, teamQuery);
  // The pinned class row is not a team, so it stays out of name filtering; it is
  // simply hidden while a search query is active.
  const showPersonalRow = !hasQuery;

  // Toasts name the team; ids are opaque (Keycloak group ids), so resolve.
  const teamLabel = (teamId: string) => teams.find((team) => team.id === teamId)?.name ?? teamId;

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
    markPending(teamId, "enabled");
    try {
      await enableCapability({
        capabilityId: capability.id,
        teamId,
        enableTeamCapabilityRequest: { settings },
      }).unwrap();
      showSuccess({
        summary: t("rework.admin.capabilities.matrix.enabledToast", { team: teamLabel(teamId) }),
      });
      setEditingTeamId(null);
    } catch {
      unmarkPending(teamId);
      showError({ summary: t("rework.admin.capabilities.matrix.enableError") });
    }
  };

  /** Opt the team out (`disable`) or clear its explicit position (`default`). */
  const submitOff = async (teamId: string, mode: "disable" | "default") => {
    if (!capability) return;
    const keys = OFF_TOAST_KEYS[mode];
    markPending(teamId, mode === "disable" ? "disabled" : "default");
    try {
      const result = await disableCapability({ capabilityId: capability.id, teamId, mode }).unwrap();
      const suspended = result.suspended_instances ?? 0;
      onSuspended(capability.id, suspended);
      if (suspended > 0) {
        showWarn({ summary: t(keys.suspended, { team: teamLabel(teamId), count: suspended }) });
      } else {
        showSuccess({ summary: t(keys.done, { team: teamLabel(teamId) }) });
      }
    } catch {
      unmarkPending(teamId);
      showError({ summary: t(keys.error) });
    }
  };

  const personalLabel = t("rework.admin.capabilities.matrix.personal.label");

  /** Set the personal-space class tri-state (RFC §8.4) for the whole class at
   * once. Uses the same optimistic spinner mechanics as a team row, keyed by
   * the reserved `PERSONAL_SCOPE_ROW_ID`. */
  const submitPersonalScope = async (next: TeamCapabilityChoice) => {
    if (!capability) return;
    const scope = next === "enabled" ? "enabled" : next === "disabled" ? "disabled" : "default";
    const keys = PERSONAL_TOAST_KEYS[scope];
    markPending(PERSONAL_SCOPE_ROW_ID, next);
    try {
      const result = await setPersonalScope({
        capabilityId: capability.id,
        setCapabilityPersonalScopeRequest: { scope },
      }).unwrap();
      const suspended = result.suspended_instances ?? 0;
      onSuspended(capability.id, suspended);
      if (suspended > 0 && "suspended" in keys) {
        showWarn({ summary: t(keys.suspended, { team: personalLabel, count: suspended }) });
      } else {
        showSuccess({ summary: t(keys.done, { team: personalLabel }) });
      }
    } catch {
      unmarkPending(PERSONAL_SCOPE_ROW_ID);
      showError({ summary: t(keys.error) });
    }
  };

  const selectPersonalChoice = (current: TeamCapabilityChoice, next: TeamCapabilityChoice) => {
    if (busy || next === current) return;
    if (next === "enabled" && requiresSettings) return;
    void submitPersonalScope(next);
  };

  const selectChoice = (teamId: string, current: TeamCapabilityChoice, next: TeamCapabilityChoice) => {
    if (busy || next === current) return;
    if (next === "enabled") {
      startEnable(teamId);
      return;
    }
    // Leaving "enabled" (or switching between off positions) closes a form
    // that might still be open for this team.
    setEditingTeamId((cur) => (cur === teamId ? null : cur));
    void submitOff(teamId, next === "disabled" ? "disable" : "default");
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
            {showPersonalRow &&
              (() => {
                const personalChoice = capabilityPersonalScopeChoice(capability);
                const pendingChoice = pendingByTeam[PERSONAL_SCOPE_ROW_ID];
                const isPending = pendingChoice !== undefined;
                const displayChoice = pendingChoice ?? personalChoice;
                return (
                  <li
                    key={PERSONAL_SCOPE_ROW_ID}
                    className={`${styles.teamRow} ${styles.personalRow}`}
                    aria-busy={isPending}
                  >
                    <div className={styles.personalMain}>
                      <span className={styles.teamName}>{personalLabel}</span>
                      <span className={styles.personalSub}>{t("rework.admin.capabilities.matrix.personal.hint")}</span>
                    </div>
                    <div className={styles.teamActions}>
                      {isPending && <span className={styles.spinner} aria-hidden="true" />}
                      <ButtonGroup
                        size="small"
                        color="primary"
                        selectedIndex={CHOICES.indexOf(displayChoice)}
                        onSelectedIndexChange={(index) => selectPersonalChoice(displayChoice, CHOICES[index])}
                        items={CHOICES.map((target) => ({
                          label: t(CHOICE_LABEL_KEY[target]),
                          disabled: busy || (target === "enabled" && requiresSettings),
                        }))}
                      />
                    </div>
                  </li>
                );
              })()}
            {visibleTeams.map((team) => {
              const choice = teamCapabilityChoice(capability, team.id);
              const off = !isCapabilityOnForTeam(capability, team.id);
              const isEditing = editingTeamId === team.id;
              // While a change is in flight the segment shows the admin's
              // click, not the not-yet-refetched server state.
              const pendingChoice = pendingByTeam[team.id];
              const isPending = pendingChoice !== undefined;
              const displayChoice = pendingChoice ?? choice;
              return (
                <li
                  key={team.id}
                  className={`${styles.teamRow} ${off && !isEditing && !isPending ? styles.dimmed : ""}`}
                  aria-busy={isPending}
                >
                  <div className={styles.teamMain}>
                    <span className={styles.teamName} title={team.name}>
                      {team.name}
                    </span>
                  </div>
                  <div className={styles.teamActions}>
                    {isPending && <span className={styles.spinner} aria-hidden="true" />}
                    <ButtonGroup
                      size="small"
                      color="primary"
                      variant="radio"
                      aria-label={t("rework.admin.capabilities.matrix.rowControlAria", { team: team.name })}
                      selectedIndex={CHOICES.indexOf(displayChoice)}
                      onSelectedIndexChange={(index) => selectChoice(team.id, displayChoice, CHOICES[index])}
                      items={CHOICES.map((target) => ({
                        label: t(CHOICE_LABEL_KEY[target]),
                        disabled: busy || (target === "enabled" && isEditing),
                      }))}
                    />
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
