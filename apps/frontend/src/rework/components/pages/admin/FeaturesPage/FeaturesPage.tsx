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

// Organization Capabilities dashboard: agent templates and pod capability offers
// with their organization default-on switch, models in their own panel. The
// Knowledge Bases and Apps tabs still read the legacy enablement catalog.

import Button from "@shared/atoms/Button/Button.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { toIconType } from "@shared/utils/Type.ts";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendFeatureFlag } from "@hooks/useFrontendFeatureFlag.ts";
import { useAdminCapabilitiesQuery } from "../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements";
import type { CapabilityEnablementItem } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { skipToken } from "@reduxjs/toolkit/query";
import {
  useLazyOrganizationCapabilityRevokeImpactQuery,
  useOrganizationAgentsQuery,
  useOrganizationCapabilitiesQuery,
  useSetOrganizationAgentDefaultMutation,
  useSetOrganizationCapabilityDefaultMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  AffectedAgentInstance,
  AgentEnablement,
  CapabilityInventoryOffer,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./FeaturesPage.module.css";
import { OrganizationCapabilities } from "./OrganizationCapabilities";
import { OrganizationModels } from "./OrganizationModels";
import { SuspendedInstancesDrawer } from "./SuspendedInstancesDrawer.tsx";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import {
  capabilityLabel,
  enabledTeamCount,
  hasAgentInstanceLifecycle,
  requiresTeamSettings,
} from "./capabilityEnablement";

// Tabs: "tool" lists pod capability offers, "agent" agent templates, "model" the organization models;
// "knowledge_base" and "app" (behind the deployment flag) list the legacy enablement catalog.
type CapabilityKind = "tool" | "agent" | "model" | "app" | "knowledge_base";
const CORE_KIND_FILTERS: CapabilityKind[] = ["tool", "agent", "model", "knowledge_base"];

// A pod offer shares the default-on switch; (pod, capability) is its identity.
type DefaultOnRow = CapabilityEnablementItem | CapabilityInventoryOffer;
const isOffer = (row: DefaultOnRow): row is CapabilityInventoryOffer => "descriptor" in row;
const defaultOnKey = (row: DefaultOnRow) => (isOffer(row) ? `${row.runtime_id}/${row.capability_id}` : row.id);

export default function FeaturesPage({ organizationId }: { organizationId: string }) {
  const [kindFilter, setKindFilter] = useState<CapabilityKind>("agent");
  // Keyed on the selected tab, not the active one: the active tab depends on this flag.
  const { enabled: applicationsEnabled } = useFrontendFeatureFlag(
    "enableApplications",
    kindFilter === "agent" || kindFilter === "model" || kindFilter === "tool",
  );
  const kindFilters: CapabilityKind[] = applicationsEnabled ? [...CORE_KIND_FILTERS, "app"] : CORE_KIND_FILTERS;
  const activeKindFilter: CapabilityKind = !applicationsEnabled && kindFilter === "app" ? "tool" : kindFilter;
  const discoveringAgents = activeKindFilter === "agent";
  const discoveringModels = activeKindFilter === "model";
  const discoveringCapabilities = activeKindFilter === "tool";
  // Models and capabilities render their own organization panel below the tabs.
  const organizationPanel = discoveringModels || discoveringCapabilities;
  const organizationCatalog = discoveringAgents || organizationPanel;
  const discovery = useOrganizationAgentsQuery(discoveringAgents ? { organizationId } : skipToken, {
    refetchOnMountOrArgChange: true,
  });
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();

  const legacy = useAdminCapabilitiesQuery(undefined, { skip: organizationCatalog });
  const { data } = legacy;
  const { isLoading, isError } = organizationPanel
    ? { isLoading: false, isError: false }
    : discoveringAgents
      ? discovery
      : legacy;
  const [setOrganizationDefault, { isLoading: isTogglingOrganizationDefault }] =
    useSetOrganizationAgentDefaultMutation();
  const [setOfferDefault, { isLoading: isTogglingOfferDefault }] = useSetOrganizationCapabilityDefaultMutation();
  const isTogglingDefault = isTogglingOrganizationDefault || isTogglingOfferDefault;

  // Live impact preview fired on demand when the disable-confirmation dialog
  // opens for a pod offer: the instances turning default-on off would stop.
  const [fetchOfferRevokeImpact, offerRevokeImpact] = useLazyOrganizationCapabilityRevokeImpactQuery();

  // A pod offer's defaultOnKey.
  const [suspendedKey, setSuspendedKey] = useState<string | null>(null);
  const [platformBindingsPanelOpen, setPlatformBindingsPanelOpen] = useState(false);
  const [pendingDefaultOff, setPendingDefaultOff] = useState<DefaultOnRow | null>(null);
  const [showAffected, setShowAffected] = useState(false);
  // Which row's mutation is in flight — NOT just a boolean. Disabling every
  // switch off `isTogglingDefault` used to include the one the admin just
  // clicked, which still holds native focus at that instant: yanking
  // `disabled` onto a focused control forces the browser to blur it and,
  // in Chromium, silently scrollIntoView() the nearest scroll container
  // (here `html`, kept `overflow: hidden` in styles/index.css) — no visible
  // scrollbar, no wheel response, only a reload undoes it. Excluding the
  // in-flight row's own id from the disabled check keeps every *other*
  // switch guarded against a concurrent submit without ever disabling the
  // one element that's still focused.
  const [togglingCapabilityId, setTogglingCapabilityId] = useState<string | null>(null);
  useEffect(() => {
    setPendingDefaultOff(null);
    setSuspendedKey(null);
  }, [organizationId, kindFilter]);

  // Synchronous, ref-backed guard against double-invoking applyDefaultOn for
  // the same capability id. A rapid double-click on the same row (the
  // always-undebounced "turn default-on on" path in onToggleDefault, below)
  // fires two calls before React has re-rendered — a togglingCapabilityId
  // state check alone can't see the first call's update in time. Without
  // this, both calls' `finally` blocks race to clear the single
  // togglingCapabilityId, and whichever resolves first can transiently
  // re-disable the still-in-flight row's Switch while it's still focused —
  // reintroducing the exact Chromium forced-blur bug the exclusion above
  // was written to prevent.
  const inFlightDefaultOnIdRef = useRef<string | null>(null);

  const capabilities = (data?.items ?? []).filter((cap) => cap.kind === activeKindFilter);
  const rowIsUnused = (capability: CapabilityEnablementItem) => enabledTeamCount(capability) === 0;

  // Served from the cache OrganizationCapabilities already holds, so the drawer follows refetches.
  const { data: offerPods } = useOrganizationCapabilitiesQuery(
    discoveringCapabilities && suspendedKey ? { organizationId } : skipToken,
  );
  const suspendedOffer =
    offerPods?.flatMap((pod) => pod.capabilities).find((offer) => defaultOnKey(offer) === suspendedKey) ?? null;
  // A personal space is named by its owner, never by its stored identifier.
  const spaceLabel = (instance: AffectedAgentInstance) =>
    instance.space_kind === "personal"
      ? [t("rework.sidebar.team.userTeam"), instance.owner_name].filter(Boolean).join(" - ")
      : instance.space_name;
  const offerName = (offer: CapabilityInventoryOffer) =>
    t(offer.descriptor.name, { defaultValue: offer.descriptor.name });
  const pendingOffer = pendingDefaultOff && isOffer(pendingDefaultOff) ? pendingDefaultOff : null;
  // Agent templates name what the organization loses; pod offers keep the generic copy.
  const defaultOffCopyVariant = discoveringAgents ? "organization" : "generic";
  // Organization pages are read-only except for agent and offer default-on.
  const canToggleDefault = (row: DefaultOnRow) => discoveringAgents || isOffer(row);

  const writeDefaultOn = (row: DefaultOnRow, default_on: boolean) =>
    isOffer(row)
      ? setOfferDefault({
          organizationId,
          runtimeId: row.runtime_id,
          capabilityId: row.capability_id,
          setDefaultOnRequest: { default_on },
        }).unwrap()
      : setOrganizationDefault({ organizationId, agentId: row.id, setDefaultOnRequest: { default_on } }).unwrap();

  const applyDefaultOn = async (capability: DefaultOnRow, nextValue: boolean) => {
    if (!canToggleDefault(capability)) return;
    const key = defaultOnKey(capability);
    if (inFlightDefaultOnIdRef.current === key) {
      return;
    }
    inFlightDefaultOnIdRef.current = key;
    setTogglingCapabilityId(key);
    try {
      await writeDefaultOn(capability, nextValue);
      showSuccess({
        summary: t(
          nextValue
            ? "rework.admin.capabilities.organizationDefaultOnToast"
            : "rework.admin.capabilities.organizationDefaultOffToast",
        ),
      });
    } catch (error) {
      showError({
        summary: t("rework.admin.capabilities.defaultToggleError"),
        detail: normalizeApiError(error).detail,
      });
    } finally {
      inFlightDefaultOnIdRef.current = null;
      setTogglingCapabilityId(null);
    }
  };

  const onToggleDefault = (capability: DefaultOnRow) => {
    if (!canToggleDefault(capability)) return;
    if (capability.default_on) {
      // Turning default-on off revokes inherited access and can stop dependent
      // instances — confirm before firing, and preview an offer's impact.
      setPendingDefaultOff(capability);
      setShowAffected(false);
      if (isOffer(capability)) {
        void fetchOfferRevokeImpact({
          organizationId,
          runtimeId: capability.runtime_id,
          capabilityId: capability.capability_id,
        });
      }
    } else {
      void applyDefaultOn(capability, true);
    }
  };

  // Concrete impact for the disable-confirmation dialog: how many working agents
  // this default-off would stop, plus the affected-agent drill-down. While
  // the preview is still loading we render nothing extra — the dialog keeps its
  // generic message and stays actionable.
  const renderImpactDetails = () => {
    const instances = offerRevokeImpact.data;
    if (!pendingOffer || offerRevokeImpact.isFetching || !instances) return null;
    return (
      <div className={styles.impact}>
        <p className={instances.length > 0 ? styles.impactWarn : styles.impactNone}>
          {instances.length > 0
            ? t("rework.admin.capabilities.defaultOffConfirm.impact", { count: instances.length })
            : t("rework.admin.capabilities.defaultOffConfirm.impactNone")}
        </p>
        {instances.length > 0 && (
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
                {instances.map((instance) => (
                  <li key={instance.agent_instance_id} className={styles.affectedItem}>
                    {t("rework.admin.capabilities.defaultOffConfirm.affectedAgent", {
                      name: instance.display_name,
                      team: spaceLabel(instance),
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

  // Per-team management is not available on organization pages: the action stays visible, disabled.
  const manageTeamsCell = (dimmed: boolean) => (
    <div className={`${styles.actionsCell} ${dimmed ? styles.dimmed : ""}`}>
      <Button
        color="on-surface"
        variant="outlined"
        size="small"
        icon={{ category: "outlined", type: "groups" }}
        disabled
      >
        {t("rework.admin.capabilities.manageTeams")}
      </Button>
    </div>
  );

  const defaultOnCell = (cap: DefaultOnRow) => {
    // A required team setting, or an offer its pod no longer advertises, blocks turning default-on
    // on, never off. The blocked state changes only through the confirmation dialog, so swapping
    // the wrapped and bare Switch never takes focus away from it.
    const blockedOn = !cap.default_on && (isOffer(cap) ? !cap.advertised : requiresTeamSettings(cap));
    const control = (
      <Switch
        size="small"
        checked={cap.default_on}
        disabled={
          !canToggleDefault(cap) || blockedOn || (isTogglingDefault && togglingCapabilityId !== defaultOnKey(cap))
        }
        onChange={() => onToggleDefault(cap)}
        aria-label={t("rework.admin.capabilities.col.defaultOn")}
      />
    );
    return (
      <div className={styles.centered}>
        {blockedOn && !isOffer(cap) ? (
          <Tooltip text={t("rework.admin.capabilities.defaultOnRequiresSettingsHint")}>{control}</Tooltip>
        ) : (
          control
        )}
      </div>
    );
  };

  const healthCell = (suspended: number, onOpen: () => void) => (
    <div className={styles.centered}>
      {suspended > 0 ? (
        // A button, not a span, so it is keyboard-reachable and announced as actionable.
        <button
          type="button"
          className={styles.healthWarnButton}
          onClick={onOpen}
          aria-label={t("rework.admin.capabilities.health.suspendedAction", { count: suspended })}
        >
          <Icon category="outlined" type="warning" />
          {t("rework.admin.capabilities.health.suspended", { count: suspended })}
        </button>
      ) : (
        <span className={styles.healthNeutral}>{t("rework.admin.capabilities.health.healthy")}</span>
      )}
    </div>
  );

  const columns: (DataTableColumn<CapabilityEnablementItem> & {
    field?: "defaultOn" | "identity" | "health" | "actions";
  })[] = [
    {
      field: "defaultOn",
      label: t("rework.admin.capabilities.col.defaultOn"),
      size: "1fr",
      cellRenderer: defaultOnCell,
    },
    {
      field: "identity",
      label: t("rework.admin.capabilities.col.capability"),
      size: "3fr",
      cellRenderer: (cap) => (
        <EntityIdentity
          name={capabilityLabel(t, cap)}
          icon={toIconType(cap.icon, "tune")}
          sourceId={cap.source_id}
          runtimeId={cap.runtime_id}
          version={cap.public_version}
          dimmed={rowIsUnused(cap)}
        />
      ),
    },
    {
      label: t("rework.admin.capabilities.col.enabledTeams"),
      size: "1fr",
      cellRenderer: (cap) => {
        const count = enabledTeamCount(cap);
        if (count === null) {
          // Default-on with no team roster from the backend — "unknown", not "0".
          return (
            <div className={styles.centered}>
              <Tooltip text={t("rework.admin.capabilities.enabledTeams.unknownHint")}>
                <span className={styles.countUnknown}>{t("rework.admin.capabilities.enabledTeams.unknown")}</span>
              </Tooltip>
            </div>
          );
        }
        // Reaches no team at all — an empty cell, not "0".
        if (count === 0) return <div className={styles.centered} />;
        const label = t("rework.admin.capabilities.enabledTeams.teams", { count });
        const stack = (
          <span className={`${styles.countStack} ${rowIsUnused(cap) ? styles.dimmed : ""}`}>
            <span className={styles.count} aria-label={label} title={label}>
              <Icon category="outlined" type="groups" />
              {count}
            </span>
          </span>
        );
        return (
          <div className={styles.centered}>
            {cap.default_on ? (
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
    // Agents and pod offers render their own health cell under this header.
    ...(hasAgentInstanceLifecycle(activeKindFilter)
      ? [{ field: "health" as const, label: t("rework.admin.capabilities.col.health"), size: "1fr" }]
      : []),
    {
      field: "actions",
      label: t("rework.admin.capabilities.col.actions"),
      // Keep the icon and label clear of the outline at desktop widths.
      size: "1.55fr",
      cellRenderer: (cap) => manageTeamsCell(rowIsUnused(cap)),
    },
  ];

  const agents = discovery.isError ? [] : (discovery.currentData ?? []);
  const discoveryColumns: DataTableColumn<AgentEnablement>[] = columns.map((column) => ({
    label: column.label,
    size: column.size,
    cellRenderer: (agent) => {
      // Reuse the existing controls; access and instance health are subsequent lots.
      if (["defaultOn", "identity", "actions"].includes(column.field ?? "")) {
        return column.cellRenderer?.(agent);
      }
      return <div className={styles.centered} />;
    },
  }));
  // Pod offers keep the catalog layout with the organization default-on switch and health.
  // Access and per-team management remain empty or disabled for now.
  const offerColumns: DataTableColumn<CapabilityInventoryOffer>[] = columns.map((column) => ({
    label: column.label,
    size: column.size,
    cellRenderer: (offer) =>
      column.field === "defaultOn" ? (
        defaultOnCell(offer)
      ) : column.field === "identity" ? (
        <EntityIdentity
          name={offerName(offer)}
          icon={toIconType(offer.descriptor.icon, "tune")}
          sourceId={offer.capability_id}
          runtimeId={offer.runtime_id}
          version={offer.descriptor.public_version}
          dimmed={!offer.advertised}
        />
      ) : column.field === "health" ? (
        healthCell(offer.unusable_instances.length, () => setSuspendedKey(defaultOnKey(offer)))
      ) : column.field === "actions" ? (
        manageTeamsCell(!offer.advertised)
      ) : (
        <div className={styles.centered} />
      ),
  }));
  const rowCount = discoveringAgents ? agents.length : capabilities.length;
  const suspendedDrawer = suspendedOffer
    ? {
        name: offerName(suspendedOffer),
        instances: suspendedOffer.unusable_instances.map((instance) => ({
          spaceId: instance.space_id,
          spaceName: spaceLabel(instance),
          displayName: instance.display_name,
        })),
      }
    : null;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.admin.capabilities.title")}
        subtitle={t("rework.admin.capabilities.subtitle")}
        actions={
          discoveringModels && (
            <Button
              color="on-surface"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "tune" }}
              onClick={() => setPlatformBindingsPanelOpen(true)}
            >
              {t("rework.admin.platformModelBindings.openButton")}
            </Button>
          )
        }
        tabs={
          <ButtonGroup
            size="small"
            color="secondary"
            variant="radio"
            aria-label={t("rework.admin.capabilities.kindFilter.aria")}
            selectedIndex={kindFilters.indexOf(activeKindFilter)}
            onSelectedIndexChange={(index) => setKindFilter(kindFilters[index])}
            items={kindFilters.map((kind) => ({
              label: t(`rework.admin.capabilities.kindFilter.${kind}`),
            }))}
          />
        }
      />

      {discoveringModels && (
        <OrganizationModels
          key={organizationId}
          organizationId={organizationId}
          defaultsOpen={platformBindingsPanelOpen}
          onCloseDefaults={() => setPlatformBindingsPanelOpen(false)}
        />
      )}
      {discoveringCapabilities && (
        <OrganizationCapabilities
          key={organizationId}
          organizationId={organizationId}
          capabilityColumns={offerColumns}
        />
      )}

      {isLoading && <p className={styles.status}>{t("rework.admin.capabilities.loading")}</p>}
      {isError && <p className={styles.statusError}>{t("rework.admin.capabilities.loadError")}</p>}

      {!organizationPanel && !isLoading && !isError && rowCount === 0 && (
        <PageEmptyState
          icon="tune"
          message={t(
            activeKindFilter === "agent"
              ? "rework.admin.capabilities.emptyAgents"
              : activeKindFilter === "app"
                ? "rework.admin.capabilities.emptyApps"
                : "rework.admin.capabilities.emptyKnowledgeBases",
          )}
        />
      )}

      {!organizationPanel &&
        !isLoading &&
        !isError &&
        rowCount > 0 &&
        (discoveringAgents ? (
          <DataTable columns={discoveryColumns} data={agents} size="medium" />
        ) : (
          <DataTable columns={columns} data={capabilities} rowKey={(capability) => capability.id} size="medium" />
        ))}

      <ConfirmationDialog
        open={pendingDefaultOff !== null}
        title={t(`rework.admin.capabilities.defaultOffConfirm.${defaultOffCopyVariant}Title`)}
        message={t(`rework.admin.capabilities.defaultOffConfirm.${defaultOffCopyVariant}Message`)}
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
      <SuspendedInstancesDrawer
        title={
          suspendedDrawer ? t("rework.admin.capabilities.suspendedDrawer.title", { name: suspendedDrawer.name }) : ""
        }
        instances={suspendedDrawer?.instances ?? []}
        open={suspendedDrawer !== null}
        onClose={() => setSuspendedKey(null)}
      />
    </div>
  );
}
