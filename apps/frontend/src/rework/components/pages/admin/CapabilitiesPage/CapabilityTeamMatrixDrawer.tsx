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
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { TuningFieldRenderer } from "../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer.tsx";
import styles from "./CapabilityTeamMatrixDrawer.module.css";
import {
  filterTeamsByName,
  isCapabilityOnForTeam,
  seedSettingsFromFields,
  sortTeamsForMatrix,
  teamCapabilityChoice,
  teamMatrixStatus,
  type TeamCapabilityChoice,
} from "./capabilityEnablement";

interface CapabilityTeamMatrixDrawerProps {
  capability: CapabilityEnablementItem | null;
  teams: Team[];
  /** `useListAllTeamsQuery` in flight — the roster isn't `teams.length === 0`, it's unknown yet. */
  teamsLoading: boolean;
  /** `useListAllTeamsQuery` failed — must read as an error, never as an empty registry. */
  teamsError: boolean;
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

export function CapabilityTeamMatrixDrawer({
  capability,
  teams,
  teamsLoading,
  teamsError,
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
  const busy = isEnabling || isDisabling;
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
      for (const [teamId, choice] of Object.entries(prev)) {
        if (teamCapabilityChoice(capability, teamId) !== choice) {
          next[teamId] = choice;
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
  const [orderedTeams, setOrderedTeams] = useState<Team[]>(teams);
  useEffect(() => {
    setTeamQuery("");
    const snapshot = capabilityRef.current;
    setOrderedTeams(snapshot ? sortTeamsForMatrix(teams, snapshot) : teams);
  }, [capability?.id, open, teams]);

  const fields = capability?.team_settings_fields ?? [];
  const hasSettings = fields.length > 0;

  const hasQuery = teamQuery.trim() !== "";
  const visibleTeams = filterTeamsByName(orderedTeams, teamQuery);
  // `teams`, not the sorted snapshot: the registry-empty check must reflect
  // the live query result immediately, not wait for the sort effect to
  // re-run — otherwise a freshly-loaded roster can flash "no teams" for a frame.
  const registryEmpty = teams.length === 0;
  const status = teamMatrixStatus({
    teamsLoading,
    teamsError,
    registryEmpty,
    hasQuery,
    visibleCount: visibleTeams.length,
  });

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

          {status === "loading" && (
            <p className={styles.hint} role="status">
              {t("rework.admin.capabilities.matrix.teamsLoading")}
            </p>
          )}

          {status === "error" && (
            <p className={styles.error} role="alert">
              {t("rework.admin.capabilities.matrix.teamsError")}
            </p>
          )}

          {status !== "loading" && status !== "error" && (
            <>
              <SearchField
                value={teamQuery}
                onChange={setTeamQuery}
                placeholder={t("rework.admin.capabilities.matrix.searchPlaceholder")}
                clearAriaLabel={t("rework.admin.capabilities.matrix.clearSearch")}
                autoFocus
              />

              {status === "registryEmpty" && (
                <p className={styles.hint}>{t("rework.admin.capabilities.matrix.noTeams")}</p>
              )}

              {status === "searchEmpty" && (
                <p className={styles.hint}>{t("rework.admin.capabilities.matrix.searchEmpty")}</p>
              )}

              {status === "ready" && (
                <ul className={styles.teamList}>
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
                              <Button
                                color="on-surface"
                                variant="text"
                                size="small"
                                onClick={() => setEditingTeamId(null)}
                              >
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
              )}
            </>
          )}
        </div>
      )}
    </InlineDrawer>
  );
}
