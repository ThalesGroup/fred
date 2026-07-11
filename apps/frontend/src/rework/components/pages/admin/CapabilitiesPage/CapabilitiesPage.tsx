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
// scope badges + enabled-team counts, the platform default-on toggle, a health
// column, and (via the drawer) the per-team tri-state matrix. Consumes only the
// generated enablement hooks — no hand-written fetch or response types.

import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { IconType } from "@shared/utils/Type.ts";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAdminCapabilitiesQuery,
  useListTeamsQuery,
  useSetCapabilityDefaultOnMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { CapabilityTeamMatrixDrawer } from "./CapabilityTeamMatrixDrawer.tsx";
import { enabledTeamCount, scopeBadge } from "./capabilityEnablement";
import styles from "./CapabilitiesPage.module.css";

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
  const [matrixCapability, setMatrixCapability] = useState<CapabilityEnablementItem | null>(null);
  const [pendingDefaultOff, setPendingDefaultOff] = useState<CapabilityEnablementItem | null>(null);

  const capabilities = data?.items ?? [];

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
      label: t("rework.admin.capabilities.col.capability"),
      size: "2.4fr",
      cellRenderer: (cap) => (
        <div className={styles.capCell}>
          <Icon category="outlined" type={cap.icon as IconType} />
          <div className={styles.capText}>
            <span className={styles.capName}>{t(cap.name, { defaultValue: cap.name })}</span>
            <span className={styles.capVersion}>v{cap.version}</span>
          </div>
        </div>
      ),
    },
    {
      label: t("rework.admin.capabilities.col.scope"),
      size: "1.2fr",
      cellRenderer: (cap) => {
        const badge = scopeBadge(cap.team_scope);
        return (
          <span className={styles.scopeBadge} data-tone={badge.tone}>
            {t(badge.labelKey)}
          </span>
        );
      },
    },
    {
      label: t("rework.admin.capabilities.col.enabledTeams"),
      size: "1fr",
      cellRenderer: (cap) => <span className={styles.count}>{enabledTeamCount(cap)}</span>,
    },
    {
      label: t("rework.admin.capabilities.col.defaultOn"),
      size: "1fr",
      cellRenderer: (cap) => (
        <Switch
          checked={cap.default_on}
          disabled={isTogglingDefault}
          onChange={() => onToggleDefault(cap)}
          aria-label={t("rework.admin.capabilities.col.defaultOn")}
        />
      ),
    },
    {
      label: t("rework.admin.capabilities.col.health"),
      size: "1fr",
      cellRenderer: (cap) => {
        const suspended = suspendedByCapability[cap.id];
        if (suspended && suspended > 0) {
          return (
            <span className={styles.healthWarn}>
              <Icon category="outlined" type="warning" />
              {t("rework.admin.capabilities.health.suspended", { count: suspended })}
            </span>
          );
        }
        return (
          <Tooltip text={t("rework.admin.capabilities.health.pending")}>
            <span className={styles.healthNeutral}>—</span>
          </Tooltip>
        );
      },
    },
    {
      label: t("rework.admin.capabilities.col.actions"),
      size: "1fr",
      cellRenderer: (cap) => (
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "groups" }}
          onClick={() => setMatrixCapability(cap)}
        >
          {t("rework.admin.capabilities.manageTeams")}
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t("rework.admin.capabilities.title")}</h1>
        <p className={styles.subtitle}>{t("rework.admin.capabilities.subtitle")}</p>
      </header>

      {isLoading && <p className={styles.status}>{t("rework.admin.capabilities.loading")}</p>}
      {isError && <p className={styles.statusError}>{t("rework.admin.capabilities.loadError")}</p>}

      {!isLoading && !isError && capabilities.length === 0 && (
        <PageEmptyState icon="tune" message={t("rework.admin.capabilities.empty")} />
      )}

      {!isLoading && !isError && capabilities.length > 0 && <DataTable columns={columns} data={capabilities} />}

      <CapabilityTeamMatrixDrawer
        capability={matrixCapability}
        teams={teams}
        open={matrixCapability !== null}
        onClose={() => setMatrixCapability(null)}
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
