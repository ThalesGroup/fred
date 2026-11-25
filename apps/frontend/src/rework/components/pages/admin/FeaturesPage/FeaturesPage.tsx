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
// Applications share offer governance; Knowledge Bases register their dedicated collectors here.

import IconButton from "@shared/atoms/IconButton/IconButton";
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
import { applicationLocaleText } from "@rework/features/applications/applicationI18n";
import { OrganizationCapabilities } from "./OrganizationCapabilities";
import { CapabilityPlatformDrawer } from "./CapabilityPlatformDrawer";
import { platformPanelFor } from "../../../../features/capabilities/platformPanelRegistry";
import McpConnectionsPage from "../McpConnectionsPage/McpConnectionsPage";
import OrganizationApplications from "./OrganizationApplications";
import OrganizationKnowledgeBases from "./OrganizationKnowledgeBases";
import { OrganizationModels } from "./OrganizationModels";
import { SuspendedInstancesDrawer } from "./SuspendedInstancesDrawer.tsx";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import { capabilityLabel, hasAgentInstanceLifecycle } from "./capabilityEnablement";

// Tabs: "tool" lists pod capability offers, "agent" agent templates, "model" the organization models;
// Applications share organization governance; Knowledge Bases use their organization registry.
type CapabilityKind = "tool" | "agent" | "model" | "mcp" | "app" | "knowledge_base";
const CORE_KIND_FILTERS: CapabilityKind[] = ["tool", "agent", "model", "mcp", "knowledge_base", "app"];

// A pod offer shares the default-on switch; (pod, capability) is its identity.
type DefaultOnRow = AgentEnablement | CapabilityInventoryOffer;
const isOffer = (row: DefaultOnRow): row is CapabilityInventoryOffer => "descriptor" in row;
const defaultOnKey = (row: DefaultOnRow) => (isOffer(row) ? `${row.source_id}/${row.capability_id}` : row.id);

export default function FeaturesPage({ organizationId }: { organizationId: string }) {
  const [kindFilter, setKindFilter] = useState<CapabilityKind>("agent");
  const kindFilters = CORE_KIND_FILTERS;
  const activeKindFilter = kindFilter;
  const discoveringAgents = activeKindFilter === "agent";
  const discoveringModels = activeKindFilter === "model";
  const discoveringCapabilities = activeKindFilter === "tool";
  // Models and capabilities render their own organization panel below the tabs.
  const organizationPanel =
    discoveringModels ||
    discoveringCapabilities ||
    activeKindFilter === "mcp" ||
    activeKindFilter === "app" ||
    activeKindFilter === "knowledge_base";
  const discovery = useOrganizationAgentsQuery(discoveringAgents ? { organizationId } : skipToken, {
    refetchOnMountOrArgChange: true,
  });
  const { t, i18n } = useTranslation();
  const { showSuccess, showError } = useToast();

  const { isLoading, isError } = organizationPanel ? { isLoading: false, isError: false } : discovery;
  const [setOrganizationDefault, { isLoading: isTogglingOrganizationDefault }] =
    useSetOrganizationAgentDefaultMutation();
  const [setOfferDefault, { isLoading: isTogglingOfferDefault }] = useSetOrganizationCapabilityDefaultMutation();
  const isTogglingDefault = isTogglingOrganizationDefault || isTogglingOfferDefault;

  // Live impact preview fired on demand when the disable-confirmation dialog
  // opens for a pod offer: the instances turning default-on off would stop.
  const [fetchOfferRevokeImpact, offerRevokeImpact] = useLazyOrganizationCapabilityRevokeImpactQuery();

  // A pod offer's defaultOnKey.
  const [platformOffer, setPlatformOffer] = useState<CapabilityInventoryOffer | null>(null);
  const [suspendedKey, setSuspendedKey] = useState<string | null>(null);
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
    setPlatformOffer(null);
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

  const rowIsUnused = (capability: AgentEnablement) => !capability.default_on;

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
    applicationLocaleText(offer.descriptor.name_by_lang ?? {}, i18n.language) ||
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
          sourceId: row.source_id,
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
      if (isOffer(capability) && activeKindFilter !== "app") {
        void fetchOfferRevokeImpact({
          organizationId,
          sourceId: capability.source_id,
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
    if (activeKindFilter === "app" || !pendingOffer || offerRevokeImpact.isFetching || !instances) return null;
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
    const blockedOn = !cap.default_on && isOffer(cap) && !cap.advertised;
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

  const columns: (DataTableColumn<AgentEnablement> & {
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
    },
    // Agents and pod offers render their own health cell under this header.
    ...(discoveringCapabilities || (activeKindFilter !== "mcp" && hasAgentInstanceLifecycle(activeKindFilter))
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
          runtimeId={offer.runtime_id ?? undefined}
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
  if (activeKindFilter === "tool")
    offerColumns.push({
      label: t("rework.admin.capabilities.col.settings"),
      size: "5rem",
      cellRenderer: (offer) => (
        <div className={styles.centered}>
          {platformPanelFor(offer.capability_id) && (
            <Tooltip text={t("rework.admin.capabilities.platformSettings")}>
              <IconButton
                variant="icon"
                size="medium"
                icon={{ category: "outlined", type: "settings" }}
                aria-label={t("rework.admin.capabilities.platformSettings")}
                disabled={!offer.advertised}
                onClick={() => setPlatformOffer(offer)}
              />
            </Tooltip>
          )}
        </div>
      ),
    });
  const rowCount = agents.length;
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
      <CapabilityPlatformDrawer
        organizationId={organizationId}
        runtimeId={platformOffer?.runtime_id ?? undefined}
        capability={
          platformOffer
            ? {
                id: platformOffer.capability_id,
                name: offerName(platformOffer),
                route_base_url: platformOffer.route_base_url,
              }
            : null
        }
        onClose={() => setPlatformOffer(null)}
      />
      <PageHeader
        title={t("rework.admin.capabilities.title")}
        subtitle={t("rework.admin.capabilities.subtitle")}
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

      {activeKindFilter === "knowledge_base" && (
        <OrganizationKnowledgeBases key={organizationId} organizationId={organizationId} />
      )}
      {activeKindFilter === "mcp" && <McpConnectionsPage spaceId={organizationId} />}
      {discoveringModels && <OrganizationModels key={organizationId} organizationId={organizationId} />}
      {activeKindFilter === "app" && <OrganizationApplications key={organizationId} organizationId={organizationId} />}
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
              : "rework.admin.capabilities.emptyKnowledgeBases",
          )}
        />
      )}

      {!organizationPanel && !isLoading && !isError && rowCount > 0 && (
        <DataTable columns={discoveryColumns} data={agents} size="medium" />
      )}

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
