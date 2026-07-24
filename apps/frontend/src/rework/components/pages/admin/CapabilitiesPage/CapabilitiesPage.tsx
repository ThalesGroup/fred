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

// Admin Capabilities dashboard (CAPAB-01 / #1981, RFC §8.5). The management
// surface over the enablement model #1980 shipped: the aggregated catalog with
// enabled-team counts, the platform default-on toggle, a health column, and
// (via the drawer) the per-team tri-state matrix. Consumes only the generated
// enablement hooks — no hand-written fetch or response types.

import Button from "@shared/atoms/Button/Button.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { toIconType } from "@shared/utils/Type.ts";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useAdminCapabilitiesQuery,
  useLazyCapabilityRevokeImpactQuery,
  useListAllTeamsQuery,
  useSetCapabilityDefaultOnMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./CapabilitiesPage.module.css";
import { CapabilityTeamMatrixDrawer } from "./CapabilityTeamMatrixDrawer.tsx";
import { SuspendedInstancesDrawer } from "./SuspendedInstancesDrawer.tsx";
import { enabledTeamCount, isCapabilityUnused as isUnused, personalSpaceCount } from "./capabilityEnablement";

// "tool" (MCP servers, etc.) vs "agent" (a control-plane-side projection of
// an agent template into this same catalog, CAPAB-01 RFC §8.6) — one admin
// surface, filtered by kind, rather than a separate page: a tool can be
// depended on by several agents, so admins need both views over the same
// underlying enablement mechanism, not two disconnected ones.
const KIND_FILTERS: Array<"tool" | "agent"> = ["tool", "agent"];

export default function CapabilitiesPage() {
  const { t } = useTranslation();
  const { showSuccess, showError, showWarn } = useToast();

  const { data, isLoading, isError } = useAdminCapabilitiesQuery();
  // The registry-governance view (`can_list_all_teams`), not the caller-scoped
  // `/teams` list — a platform admin managing per-team enablement must see
  // every team, including ones they don't personally belong to (#1981).
  const { data: teams = [], isLoading: isTeamsLoading, isError: isTeamsError } = useListAllTeamsQuery();
  const [setDefaultOn, { isLoading: isTogglingDefault }] = useSetCapabilityDefaultOnMutation();

  // Live impact preview fired on demand when the disable-confirmation dialog
  // opens — a platform-wide (no teamId) preview of what turning default-on off
  // would break right now. The resting per-capability health count in the
  // table itself comes straight from the aggregate list (#1975), not from here.
  const [fetchRevokeImpact, revokeImpact] = useLazyCapabilityRevokeImpactQuery();

  const [matrixCapabilityId, setMatrixCapabilityId] = useState<string | null>(null);
  const [suspendedCapabilityId, setSuspendedCapabilityId] = useState<string | null>(null);
  const [pendingDefaultOff, setPendingDefaultOff] = useState<CapabilityEnablementItem | null>(null);
  const [showAffected, setShowAffected] = useState(false);
  const [kindFilter, setKindFilter] = useState<"tool" | "agent">("tool");

  const allCapabilities = data?.items ?? [];
  // `kind` is optional on the generated type (added to the enablement item
  // after tools already shipped) — an absent value is a tool, same default
  // as the backend's own `CapabilityEnablementItem.kind`.
  const capabilities = allCapabilities.filter((cap) => (cap.kind ?? "tool") === kindFilter);

  // Resolved from the live query on every render — NOT snapshotted into state.
  // Every drawer mutation invalidates and refetches the list; a snapshot taken
  // at open time would keep the drawer's tri-state frozen while the table
  // behind it updates.
  const matrixCapability = capabilities.find((cap) => cap.id === matrixCapabilityId) ?? null;
  const suspendedCapability = capabilities.find((cap) => cap.id === suspendedCapabilityId) ?? null;

  const applyDefaultOn = async (capability: CapabilityEnablementItem, nextValue: boolean) => {
    try {
      const result = await setDefaultOn({
        capabilityId: capability.id,
        setCapabilityDefaultOnRequest: { default_on: nextValue },
      }).unwrap();
      const suspended = result.suspended_instances ?? 0;
      if (suspended > 0) {
        showWarn({ summary: t("rework.admin.capabilities.defaultOffSuspendedToast", { count: suspended }) });
      } else {
        showSuccess({
          summary: nextValue
            ? t("rework.admin.capabilities.defaultOnToast")
            : t("rework.admin.capabilities.defaultOffToast"),
        });
      }
    } catch {
      showError({ summary: t("rework.admin.capabilities.defaultToggleError") });
    }
  };

  const onToggleDefault = (capability: CapabilityEnablementItem) => {
    if (capability.default_on) {
      // Turning default-on off revokes inherited access team-by-team and can
      // suspend dependent instances — confirm before firing, and preview the
      // platform-wide impact (no teamId) so the admin sees what breaks.
      setPendingDefaultOff(capability);
      setShowAffected(false);
      void fetchRevokeImpact({ capabilityId: capability.id });
    } else {
      void applyDefaultOn(capability, true);
    }
  };

  const impact = revokeImpact.data;
  const impactSuspended = impact?.suspended_instances ?? 0;
  const impactUnknown = impact?.health_unknown_instances ?? 0;
  const impactInstances = impact?.instances ?? [];

  // Concrete impact for the disable-confirmation dialog: how many working agents
  // this default-off would suspend, plus the affected-agent drill-down. While
  // the preview is still loading we render nothing extra — the dialog keeps its
  // generic message and stays actionable.
  const renderImpactDetails = () => {
    if (revokeImpact.isFetching || !impact) return null;
    return (
      <div className={styles.impact}>
        <p className={impactSuspended > 0 ? styles.impactWarn : styles.impactNone}>
          {impactSuspended > 0
            ? t("rework.admin.capabilities.defaultOffConfirm.impact", { count: impactSuspended })
            : t("rework.admin.capabilities.defaultOffConfirm.impactNone")}
        </p>
        {impactUnknown > 0 && (
          <p className={styles.impactUnknown}>
            {t("rework.admin.capabilities.defaultOffConfirm.impactUnknown", { count: impactUnknown })}
          </p>
        )}
        {impactInstances.length > 0 && (
          <>
            <Button
              color="on-surface"
              variant="text"
              size="small"
              onClick={() => setShowAffected((prev) => !prev)}
              aria-expanded={showAffected}
            >
              {t(
                showAffected
                  ? "rework.admin.capabilities.defaultOffConfirm.hideAffected"
                  : "rework.admin.capabilities.defaultOffConfirm.showAffected",
              )}
            </Button>
            {showAffected && (
              <ul className={styles.affectedList}>
                {impactInstances.map((instance) => (
                  <li key={instance.agent_instance_id} className={styles.affectedItem}>
                    {t("rework.admin.capabilities.defaultOffConfirm.affectedAgent", {
                      name: instance.display_name,
                      // Resolve the opaque Keycloak group id to its team name —
                      // same pattern as SuspendedInstancesDrawer's grouping.
                      team: teams.find((team) => team.id === instance.team_id)?.name ?? instance.team_id,
                    })}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    );
  };

  const columns: DataTableColumn<CapabilityEnablementItem>[] = [
    {
      label: t("rework.admin.capabilities.col.defaultOn"),
      size: "1fr",
      cellRenderer: (cap) => (
        <div className={styles.centered}>
          <Switch
            checked={cap.default_on}
            disabled={isTogglingDefault}
            onChange={() => onToggleDefault(cap)}
            aria-label={t("rework.admin.capabilities.col.defaultOn")}
          />
        </div>
      ),
    },
    {
      label: t("rework.admin.capabilities.col.capability"),
      size: "2.4fr",
      cellRenderer: (cap) => (
        <div className={`${styles.capCell} ${isUnused(cap) ? styles.dimmed : ""}`}>
          <Icon category="outlined" type={toIconType(cap.icon, "tune")} />
          <div className={styles.capText}>
            <span className={styles.capName} title={t(cap.name, { defaultValue: cap.name })}>
              {t(cap.name, { defaultValue: cap.name })}
            </span>
            <span className={styles.capVersion}>v{cap.version}</span>
          </div>
        </div>
      ),
    },
    {
      label: t("rework.admin.capabilities.col.enabledTeams"),
      // Wider than the other 1fr columns: the two reach badges (teams,
      // personal spaces) need to sit side by side on one line, not wrap.
      size: "1.6fr",
      cellRenderer: (cap) => {
        const count = enabledTeamCount(cap);
        const personal = personalSpaceCount(cap);
        // Personal-class reach is additive to the team count — "12 teams" over
        // "40 personal spaces", one line each — because personal spaces are
        // deliberately not in `total_team_count` (RFC §8.4). A zero part says
        // nothing, so it is dropped; `null` personal means "reaches personal
        // spaces, roster unknown".
        const parts: string[] = [];
        if (count !== null && count > 0) {
          parts.push(t("rework.admin.capabilities.enabledTeams.teams", { count }));
        }
        if (personal === null) {
          parts.push(t("rework.admin.capabilities.enabledTeams.personalUnknown"));
        } else if (personal > 0) {
          parts.push(t("rework.admin.capabilities.enabledTeams.personal", { count: personal }));
        }
        const stack = (
          <span className={`${styles.countStack} ${isUnused(cap) ? styles.dimmed : ""}`}>
            {parts.map((part) => (
              <span key={part} className={styles.count}>
                {part}
              </span>
            ))}
          </span>
        );
        return (
          <div className={styles.centered}>
            {count === null ? (
              // Default-on with no team roster from the backend — "unknown", not
              // "0". The personal roster comes from the same directory, so no
              // personal part either — one "Unknown" covers both.
              <Tooltip text={t("rework.admin.capabilities.enabledTeams.unknownHint")}>
                <span className={styles.countUnknown}>{t("rework.admin.capabilities.enabledTeams.unknown")}</span>
              </Tooltip>
            ) : parts.length === 0 ? null : cap.default_on ? ( // Reaches nobody at all — an empty cell, not "0".
              // Default-on grants access by inheritance, so the counts are roster
              // headcounts rather than lists of explicit grants — say so, otherwise
              // "12 teams" looks like 12 admins clicked Enable.
              <Tooltip text={t("rework.admin.capabilities.enabledTeams.inheritedHint")}>{stack}</Tooltip>
            ) : (
              stack
            )}
          </div>
        );
      },
    },
    {
      label: t("rework.admin.capabilities.col.health"),
      size: "1fr",
      cellRenderer: (cap) => {
        // Resting health straight from the aggregate list (#1975): agents this
        // capability breaks AT REST (`suspended_instances`) vs. agents whose pod
        // was unreachable so their health can't be determined
        // (`health_unknown_instances`) — kept visually distinct.
        const suspended = cap.suspended_instances ?? 0;
        const unknown = cap.health_unknown_instances ?? 0;
        return (
          <div className={styles.centered}>
            {suspended > 0 ? (
              // Clickable: opens the drill-down of which agents, in which team,
              // this capability breaks at rest (#1975). A button, not a span, so
              // it is keyboard-reachable and announced as actionable.
              <button
                type="button"
                className={styles.healthWarnButton}
                onClick={() => setSuspendedCapabilityId(cap.id)}
                aria-label={t("rework.admin.capabilities.health.suspendedAction", { count: suspended })}
              >
                <Icon category="outlined" type="warning" />
                {t("rework.admin.capabilities.health.suspended", { count: suspended })}
              </button>
            ) : unknown > 0 ? (
              <Tooltip text={t("rework.admin.capabilities.health.unknownHint")}>
                <span className={styles.healthNeutral}>
                  {t("rework.admin.capabilities.health.unknown", { count: unknown })}
                </span>
              </Tooltip>
            ) : (
              <span className={styles.healthNeutral}>{t("rework.admin.capabilities.health.healthy")}</span>
            )}
          </div>
        );
      },
    },
    {
      label: t("rework.admin.capabilities.col.actions"),
      // Wide enough for the one-line button at desktop widths, but still a
      // shrinkable fr so narrow viewports fall back to the wrapped label
      // rather than forcing the table to overflow.
      size: "1.4fr",
      cellRenderer: (cap) => (
        // Dimmed but never disabled: an unused capability is exactly the one an
        // admin opens to grant its first team.
        <div className={`${styles.actionsCell} ${isUnused(cap) ? styles.dimmed : ""}`}>
          <Button
            color="on-surface"
            variant="outlined"
            size="small"
            icon={{ category: "outlined", type: "groups" }}
            onClick={() => setMatrixCapabilityId(cap.id)}
          >
            {t("rework.admin.capabilities.manageTeams")}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t("rework.admin.capabilities.title")}</h1>
        <p className={styles.subtitle}>{t("rework.admin.capabilities.subtitle")}</p>
      </header>

      <ButtonGroup
        size="small"
        color="primary"
        variant="radio"
        aria-label={t("rework.admin.capabilities.kindFilter.aria")}
        selectedIndex={KIND_FILTERS.indexOf(kindFilter)}
        onSelectedIndexChange={(index) => setKindFilter(KIND_FILTERS[index])}
        items={KIND_FILTERS.map((kind) => ({
          label: t(`rework.admin.capabilities.kindFilter.${kind}`),
        }))}
      />

      {isLoading && <p className={styles.status}>{t("rework.admin.capabilities.loading")}</p>}
      {isError && <p className={styles.statusError}>{t("rework.admin.capabilities.loadError")}</p>}

      {!isLoading && !isError && capabilities.length === 0 && (
        <PageEmptyState
          icon="tune"
          message={t(
            kindFilter === "agent" ? "rework.admin.capabilities.emptyAgents" : "rework.admin.capabilities.empty",
          )}
        />
      )}

      {!isLoading && !isError && capabilities.length > 0 && <DataTable columns={columns} data={capabilities} />}

      <CapabilityTeamMatrixDrawer
        capability={matrixCapability}
        teams={teams}
        teamsLoading={isTeamsLoading}
        teamsError={isTeamsError}
        open={matrixCapability !== null}
        onClose={() => setMatrixCapabilityId(null)}
      />

      <SuspendedInstancesDrawer
        capability={suspendedCapability}
        teams={teams}
        open={suspendedCapability !== null}
        onClose={() => setSuspendedCapabilityId(null)}
      />

      <ConfirmationDialog
        open={pendingDefaultOff !== null}
        title={t("rework.admin.capabilities.defaultOffConfirm.title")}
        message={t("rework.admin.capabilities.defaultOffConfirm.message")}
        details={renderImpactDetails()}
        confirmLabel={t("rework.admin.capabilities.defaultOffConfirm.confirm")}
        cancelLabel={t("rework.admin.capabilities.defaultOffConfirm.cancel")}
        criticalAction
        onConfirm={() => {
          if (pendingDefaultOff) void applyDefaultOn(pendingDefaultOff, false);
          setPendingDefaultOff(null);
        }}
        onCancel={() => setPendingDefaultOff(null)}
      />
    </div>
  );
}
