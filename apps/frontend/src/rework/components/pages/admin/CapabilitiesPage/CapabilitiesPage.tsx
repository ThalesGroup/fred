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
  useListTeamsQuery,
  useSetCapabilityDefaultOnMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./CapabilitiesPage.module.css";
import { CapabilityTeamMatrixDrawer } from "./CapabilityTeamMatrixDrawer.tsx";
import { enabledTeamCount, isCapabilityUnused as isUnused } from "./capabilityEnablement";

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
  const { data: teams = [] } = useListTeamsQuery();
  const [setDefaultOn, { isLoading: isTogglingDefault }] = useSetCapabilityDefaultOnMutation();

  // Session-observed suspended-instance counts per capability, sourced from the
  // enablement mutations (revoke / default-off). The aggregate list carries no
  // resting per-capability health count yet — that data lands with #1975.
  const [suspendedByCapability, setSuspendedByCapability] = useState<Record<string, number>>({});
  const [matrixCapabilityId, setMatrixCapabilityId] = useState<string | null>(null);
  const [pendingDefaultOff, setPendingDefaultOff] = useState<CapabilityEnablementItem | null>(null);
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

  const recordSuspended = (capabilityId: string, count: number) => {
    setSuspendedByCapability((prev) => ({ ...prev, [capabilityId]: count }));
  };

  const applyDefaultOn = async (capability: CapabilityEnablementItem, nextValue: boolean) => {
    try {
      const result = await setDefaultOn({
        capabilityId: capability.id,
        setCapabilityDefaultOnRequest: { default_on: nextValue },
      }).unwrap();
      const suspended = result.suspended_instances ?? 0;
      recordSuspended(capability.id, suspended);
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
      // suspend dependent instances — confirm before firing.
      setPendingDefaultOff(capability);
    } else {
      void applyDefaultOn(capability, true);
    }
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
      size: "1fr",
      cellRenderer: (cap) => {
        const count = enabledTeamCount(cap);
        return (
          <div className={styles.centered}>
            {count === null ? (
              // Default-on with no team roster from the backend — "unknown", not "0".
              <Tooltip text={t("rework.admin.capabilities.enabledTeams.unknownHint")}>
                <span className={styles.countUnknown}>{t("rework.admin.capabilities.enabledTeams.unknown")}</span>
              </Tooltip>
            ) : cap.default_on ? (
              // Default-on grants access by inheritance, so the count is a roster
              // headcount rather than a list of explicit grants — say so, otherwise
              // "12" looks like 12 admins clicked Enable.
              <Tooltip text={t("rework.admin.capabilities.enabledTeams.inheritedHint")}>
                <span className={styles.count}>{t("rework.admin.capabilities.enabledTeams.all", { count })}</span>
              </Tooltip>
            ) : (
              <span className={`${styles.count} ${isUnused(cap) ? styles.dimmed : ""}`}>{count}</span>
            )}
          </div>
        );
      },
    },
    {
      label: t("rework.admin.capabilities.col.health"),
      size: "1fr",
      cellRenderer: (cap) => {
        const suspended = suspendedByCapability[cap.id];
        return (
          <div className={styles.centered}>
            {suspended && suspended > 0 ? (
              <span className={styles.healthWarn}>
                <Icon category="outlined" type="warning" />
                {t("rework.admin.capabilities.health.suspended", { count: suspended })}
              </span>
            ) : (
              <Tooltip text={t("rework.admin.capabilities.health.pending")}>
                <span className={styles.healthNeutral}>—</span>
              </Tooltip>
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
        open={matrixCapability !== null}
        onClose={() => setMatrixCapabilityId(null)}
        onSuspended={recordSuspended}
      />

      <ConfirmationDialog
        open={pendingDefaultOff !== null}
        title={t("rework.admin.capabilities.defaultOffConfirm.title")}
        message={t("rework.admin.capabilities.defaultOffConfirm.message")}
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
