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
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { toIconType } from "@shared/utils/Type.ts";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendFeatureFlag } from "@hooks/useFrontendFeatureFlag.ts";
import { useUserCapabilities } from "@rework/core/hooks/useUserCapabilities";
import {
  useAdminCapabilitiesQuery,
  useLazyCapabilityRevokeImpactQuery,
  useListAllTeamsQuery,
  useSetCapabilityDefaultOnMutation,
  useSetModelReasoningMutation,
  useModelDiscoveryQuery,
  usePodChatDefaultsQuery,
  usePlatformModelBindingQuery,
  useRefreshModelDiscoveryMutation,
} from "../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements";
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
import { CapabilityTeamMatrixDrawer } from "./CapabilityTeamMatrixDrawer.tsx";
import { PlatformModelBindingsPanel } from "./PlatformModelBindingsPanel/PlatformModelBindingsPanel.tsx";
import { SuspendedInstancesDrawer } from "./SuspendedInstancesDrawer.tsx";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import {
  capabilityLabel,
  dependencyLabels,
  enabledTeamCount,
  hasReasoningControl,
  isCapabilityUnused as isUnused,
  hasAgentInstanceLifecycle,
  missingAgentDependenciesForPlatform,
  personalSpaceCount,
  requiresTeamSettings,
} from "./capabilityEnablement";
import { ModelIdentityCell } from "./ModelIdentityCell";
import { ModelDiscoveryStatus, UnverifiedRuntimeWarning } from "./ModelDiscoveryStatus";
import { partitionDiscoveredModels, splitModelSections } from "./modelSections";

// "tool" (MCP servers, etc.) vs "agent" (a control-plane-side projection of
// an agent template into this same catalog, CAPAB-01 RFC §8.6) vs "model" (a
// pod-advertised projection of one models_catalog.yaml entry, OBSERV-02 v3
// RFC §8.7) — one admin surface, filtered by kind, rather than a separate
// page: a tool can be depended on by several agents, so admins need all
// enabled views over the same underlying mechanism, not several disconnected
// pages. The optional Apps view follows the deployment-wide feature gate.
// "knowledge_base" is a control-plane projection of a published Knowledge Base
// definition: same enablement shape as an app, on its own ReBAC type, so it
// belongs on this surface rather than a page of its own.
type CapabilityKind = "tool" | "agent" | "model" | "app" | "knowledge_base";
const CORE_KIND_FILTERS: CapabilityKind[] = ["tool", "agent", "model", "knowledge_base"];

// A pod offer shares the default-on switch; (pod, capability) is its identity.
type DefaultOnRow = CapabilityEnablementItem | CapabilityInventoryOffer;
const isOffer = (row: DefaultOnRow): row is CapabilityInventoryOffer => "descriptor" in row;
const defaultOnKey = (row: DefaultOnRow) => (isOffer(row) ? `${row.runtime_id}/${row.capability_id}` : row.id);

export default function FeaturesPage({ organizationId }: { organizationId?: string } = {}) {
  const readOnly = organizationId !== undefined;
  const [kindFilter, setKindFilter] = useState<CapabilityKind>(readOnly ? "agent" : "tool");
  const discoveringAgents = readOnly && kindFilter === "agent";
  const discoveringModels = readOnly && kindFilter === "model";
  const discoveringCapabilities = readOnly && kindFilter === "tool";
  // Models and capabilities render their own organization panel below the tabs.
  const organizationPanel = discoveringModels || discoveringCapabilities;
  const organizationCatalog = discoveringAgents || organizationPanel;
  const discovery = useOrganizationAgentsQuery(discoveringAgents && organizationId ? { organizationId } : skipToken, {
    refetchOnMountOrArgChange: true,
  });
  const { t } = useTranslation();
  const { showSuccess, showError, showWarn } = useToast();
  const { canAdmin } = useUserCapabilities(organizationCatalog);
  const { enabled: applicationsEnabled } = useFrontendFeatureFlag("enableApplications", organizationCatalog);
  const kindFilters: CapabilityKind[] = applicationsEnabled ? [...CORE_KIND_FILTERS, "app"] : CORE_KIND_FILTERS;

  const legacy = useAdminCapabilitiesQuery(undefined, { skip: organizationCatalog });
  const { data, refetch: refetchCapabilities } = legacy;
  const { isLoading, isError } = organizationPanel
    ? { isLoading: false, isError: false }
    : discoveringAgents
      ? discovery
      : legacy;
  // The full registry (`can_list_all_teams`), not the caller-scoped `/teams`: an admin
  // must see teams they don't belong to. The drawer only needs ids and names, so the
  // per-team membership reads are skipped.
  const {
    data: teams = [],
    isLoading: isTeamsLoading,
    isError: isTeamsError,
  } = useListAllTeamsQuery({ includeMembership: false }, { skip: readOnly });
  const [setDefaultOn, { isLoading: isTogglingLegacyDefault }] = useSetCapabilityDefaultOnMutation();
  const [setOrganizationDefault, { isLoading: isTogglingOrganizationDefault }] =
    useSetOrganizationAgentDefaultMutation();
  const [setOfferDefault, { isLoading: isTogglingOfferDefault }] = useSetOrganizationCapabilityDefaultMutation();
  const isTogglingDefault = isTogglingLegacyDefault || isTogglingOrganizationDefault || isTogglingOfferDefault;
  // Per-model reasoning activation (REASON-01, MODEL-REASONING-ENABLEMENT-RFC.md §5).
  const [setModelReasoning, { isLoading: isTogglingReasoning }] = useSetModelReasoningMutation();

  // Live impact preview fired on demand when the disable-confirmation dialog
  // opens — a platform-wide (no teamId) preview of what turning default-on off
  // would break right now. The resting per-capability health count in the
  // table itself comes straight from the aggregate list (#1975), not from here.
  const [fetchRevokeImpact, revokeImpact] = useLazyCapabilityRevokeImpactQuery();
  const [fetchOfferRevokeImpact, offerRevokeImpact] = useLazyOrganizationCapabilityRevokeImpactQuery();

  const [matrixCapabilityId, setMatrixCapabilityId] = useState<string | null>(null);
  // A catalog row id or a pod offer's defaultOnKey.
  const [suspendedKey, setSuspendedKey] = useState<string | null>(null);
  const [platformBindingsPanelOpen, setPlatformBindingsPanelOpen] = useState(false);
  const [noDefaultModalOpen, setNoDefaultModalOpen] = useState(false);
  const [noDefaultModalPending, setNoDefaultModalPending] = useState(false);
  const [pendingDefaultOff, setPendingDefaultOff] = useState<DefaultOnRow | null>(null);
  // #2470: an agent template whose dependencies are not default-on, waiting for
  // the admin to confirm granting them alongside it. Holds the capability the
  // switch was clicked on; the missing ids are re-derived at confirm time from
  // the live list rather than snapshotted, so a dependency granted by another
  // admin (or another tab) in between is not re-granted.
  const [pendingGrantAll, setPendingGrantAll] = useState<CapabilityEnablementItem | null>(null);
  const [showAffected, setShowAffected] = useState(false);
  const [modelTab, setModelTab] = useState<"manual" | "discovered">("manual");
  const [modelDefaultsInitialTab, setModelDefaultsInitialTab] = useState<"platform" | "pods">("pods");
  const [modelFilter, setModelFilter] = useState("");
  const activeKindFilter: CapabilityKind = !applicationsEnabled && kindFilter === "app" ? "tool" : kindFilter;
  const legacyModels = activeKindFilter === "model" && !discoveringModels;
  const { data: discoveryStatus, refetch: refetchDiscoveryStatus } = useModelDiscoveryQuery(undefined, {
    skip: !legacyModels,
  });
  const {
    data: podDefaults,
    isFetching: podDefaultsFetching,
    isError: podDefaultsError,
  } = usePodChatDefaultsQuery(undefined, { skip: !legacyModels });
  const {
    data: platformModelBinding,
    isLoading: platformModelBindingLoading,
    isError: platformModelBindingError,
  } = usePlatformModelBindingQuery(undefined, {
    skip: !legacyModels,
  });
  const [refreshDiscovery, discoveryRefresh] = useRefreshModelDiscoveryMutation();
  const [modelInventoryReady, setModelInventoryReady] = useState(false);
  const [modelSourceCheckReady, setModelSourceCheckReady] = useState(false);
  const [modelRefreshError, setModelRefreshError] = useState<string | null>(null);
  const [unverifiedModelRuntimes, setUnverifiedModelRuntimes] = useState<{ runtime_id: string; base_url: string }[]>(
    [],
  );
  const [verifiedModelSourceIds, setVerifiedModelSourceIds] = useState<string[] | null>(null);
  const refreshModels = useCallback(async () => {
    try {
      const result = await refreshDiscovery().unwrap();
      setModelRefreshError(result.refresh_error ?? null);
      setUnverifiedModelRuntimes(result.unverified_runtimes ?? []);
      setVerifiedModelSourceIds(result.verified_source_ids ?? null);
      if (result.verified_source_ids?.length === 0 && !result.unverified_runtimes?.length) {
        setModelTab("manual");
      }
    } catch {
      setModelRefreshError(t("rework.admin.capabilities.discovery.refreshFailed"));
      setUnverifiedModelRuntimes([]);
      setVerifiedModelSourceIds(null);
    }
    await Promise.all([refetchCapabilities(), refetchDiscoveryStatus()]);
  }, [refreshDiscovery, refetchCapabilities, refetchDiscoveryStatus, t]);
  useEffect(() => {
    if (!legacyModels) return;
    let mounted = true;
    setModelInventoryReady(false);
    setModelSourceCheckReady(false);
    setVerifiedModelSourceIds(null);
    setUnverifiedModelRuntimes([]);
    void refetchDiscoveryStatus().then(
      (result) => {
        if (mounted && !(result && "error" in result && result.error)) setModelSourceCheckReady(true);
      },
      () => undefined,
    );
    void refreshModels().then(
      () => {
        if (mounted) setModelInventoryReady(true);
      },
      () => {
        if (mounted) setModelInventoryReady(true);
      },
    );
    return () => {
      mounted = false;
    };
  }, [legacyModels, refetchDiscoveryStatus, refreshModels]);
  const currentVerifiedSourceIds =
    verifiedModelSourceIds ?? (modelSourceCheckReady ? (discoveryStatus?.verified_source_ids ?? null) : null);
  const currentUnverifiedRuntimes =
    modelInventoryReady && verifiedModelSourceIds !== null
      ? unverifiedModelRuntimes
      : (discoveryStatus?.unverified_runtimes ?? unverifiedModelRuntimes);
  const discoveryConfigurationReady = modelSourceCheckReady || modelInventoryReady;
  const verifiedDiscoverySources = currentVerifiedSourceIds !== null && currentUnverifiedRuntimes.length === 0;
  const discoverySources = verifiedDiscoverySources
    ? (discoveryStatus?.sources ?? []).filter((source) => currentVerifiedSourceIds?.includes(source.source_id))
    : (discoveryStatus?.sources ?? []);
  const newModelIds = new Set(discoverySources.flatMap((source) => source.new_ids ?? []));
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
  // Same guard pair, same reason, for the Modèles-tab reasoning Switch: it
  // shares `Switch`, `isTogglingReasoning` spans every row like
  // `isTogglingDefault` did, and `<html>` is still `overflow: hidden` — an
  // undisabled just-clicked row here would blur+scrollIntoView identically.
  const [togglingReasoningId, setTogglingReasoningId] = useState<string | null>(null);
  const inFlightReasoningIdRef = useRef<string | null>(null);

  // Keep stale cached app rows unreachable if the deployment switch is turned
  // off while this page is mounted. The backend applies the same gate.
  const allCapabilities = (data?.items ?? []).filter((capability) => applicationsEnabled || capability.kind !== "app");
  // `kind` is optional on the generated type (added to the enablement item
  // after tools already shipped) — an absent value is a tool, same default
  // as the backend's own `CapabilityEnablementItem.kind`.
  const capabilities = allCapabilities.filter((cap) => (cap.kind ?? "tool") === activeKindFilter);
  const { manual: manualModels, discovered: advertisedDiscoveredModels } = splitModelSections(capabilities);
  const activeDiscoveredModels = verifiedDiscoverySources
    ? advertisedDiscoveredModels.filter((model) =>
        currentVerifiedSourceIds?.includes(model.model_discovery_source_id ?? ""),
      )
    : advertisedDiscoveredModels;
  const { listed: discoveredModels, unavailableIds: unavailableDiscoveredIds } = partitionDiscoveredModels(
    activeDiscoveredModels,
    discoverySources,
  );
  const hasDiscovery =
    discoveryConfigurationReady &&
    (verifiedDiscoverySources
      ? (currentVerifiedSourceIds?.length ?? 0) > 0
      : Boolean(discoverySources.length || advertisedDiscoveredModels.length));
  const visibleCapabilities = activeKindFilter === "model" && !hasDiscovery ? manualModels : capabilities;
  useEffect(() => {
    if (
      !noDefaultModalPending ||
      !legacyModels ||
      isLoading ||
      platformModelBindingLoading ||
      podDefaultsFetching ||
      (!podDefaults && !podDefaultsError) ||
      !modelInventoryReady
    )
      return;
    setNoDefaultModalPending(false);
    if (
      canAdmin &&
      !isError &&
      !platformModelBindingError &&
      !podDefaultsError &&
      !modelRefreshError &&
      !platformModelBinding?.binding &&
      podDefaults?.pods?.some((pod) => pod.reachable && !pod.effective_profile_id)
    ) {
      setNoDefaultModalOpen(true);
    }
  }, [
    legacyModels,
    canAdmin,
    isError,
    isLoading,
    modelInventoryReady,
    modelRefreshError,
    noDefaultModalPending,
    platformModelBinding?.binding,
    platformModelBindingError,
    platformModelBindingLoading,
    podDefaults,
    podDefaultsError,
    podDefaultsFetching,
  ]);
  const visibleModels = (modelTab === "manual" ? manualModels : discoveredModels).filter((model) =>
    [model.model_display_name, model.name, model.id, ...(model.model_runtime_ids ?? [])]
      .filter(Boolean)
      .some((value) => value!.toLocaleLowerCase().includes(modelFilter.trim().toLocaleLowerCase())),
  );
  const rowIsUnused = (capability: CapabilityEnablementItem) =>
    hasAgentInstanceLifecycle(capability.kind) ? isUnused(capability) : enabledTeamCount(capability) === 0;

  // Resolved from the live query on every render — NOT snapshotted into state.
  // Every drawer mutation invalidates and refetches the list; a snapshot taken
  // at open time would keep the drawer's tri-state frozen while the table
  // behind it updates.
  const matrixCapability =
    capabilities.find((cap) => cap.id === matrixCapabilityId && !unavailableDiscoveredIds.has(cap.id)) ?? null;
  const suspendedCapability = capabilities.find((cap) => cap.id === suspendedKey) ?? null;
  // Served from the cache OrganizationCapabilities already holds, so the drawer follows refetches.
  const { data: offerPods } = useOrganizationCapabilitiesQuery(
    discoveringCapabilities && organizationId && suspendedKey ? { organizationId } : skipToken,
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
  const pendingCapability = pendingDefaultOff && !isOffer(pendingDefaultOff) ? pendingDefaultOff : null;
  const pendingOffer = pendingDefaultOff && isOffer(pendingDefaultOff) ? pendingDefaultOff : null;
  const visiblePendingDefaultOff = applicationsEnabled || pendingCapability?.kind !== "app" ? pendingDefaultOff : null;
  // Each kind loses something different when default-on goes off: agent
  // instances can be suspended, an application or a Knowledge Base only loses
  // inherited access. Naming the object is what makes the dialog truthful.
  const defaultOffCopyVariant = discoveringAgents
    ? "organization"
    : pendingCapability?.kind === "app"
      ? "app"
      : pendingCapability?.kind === "knowledge_base"
        ? "knowledgeBase"
        : "generic";
  // Organization pages are read-only except for agent and offer default-on.
  const canToggleDefault = (row: DefaultOnRow) => !readOnly || discoveringAgents || isOffer(row);

  const writeDefaultOn = async (row: DefaultOnRow, default_on: boolean) => {
    if (isOffer(row)) {
      if (!organizationId) throw new Error("Capability offers belong to an organization.");
      await setOfferDefault({
        organizationId,
        runtimeId: row.runtime_id,
        capabilityId: row.capability_id,
        setDefaultOnRequest: { default_on },
      }).unwrap();
      return { default_on };
    }
    return organizationId
      ? setOrganizationDefault({ organizationId, agentId: row.id, setDefaultOnRequest: { default_on } }).unwrap()
      : setDefaultOn({ capabilityId: row.id, setCapabilityDefaultOnRequest: { default_on } }).unwrap();
  };

  const applyDefaultOn = async (capability: DefaultOnRow, nextValue: boolean) => {
    if (!canToggleDefault(capability)) return;
    const key = defaultOnKey(capability);
    if (inFlightDefaultOnIdRef.current === key) {
      return;
    }
    inFlightDefaultOnIdRef.current = key;
    setTogglingCapabilityId(key);
    try {
      const result = await writeDefaultOn(capability, nextValue);
      const suspended =
        "suspended_instances" in result && typeof result.suspended_instances === "number"
          ? result.suspended_instances
          : 0;
      if (suspended > 0) {
        showWarn({ summary: t("rework.admin.capabilities.defaultOffSuspendedToast", { count: suspended }) });
      } else {
        showSuccess({
          summary: organizationId
            ? t(
                nextValue
                  ? "rework.admin.capabilities.organizationDefaultOnToast"
                  : "rework.admin.capabilities.organizationDefaultOffToast",
              )
            : t(nextValue ? "rework.admin.capabilities.defaultOnToast" : "rework.admin.capabilities.defaultOffToast"),
        });
      }
      // A model switched off takes its reasoning down with it (REASON-01 §5.7).
      // Its own toast, in addition to the one above rather than instead of it:
      // the row's reasoning switch flips on its own when the list refetches,
      // and an unexplained state change on an admin screen reads as a bug.
      if ("reasoning_disabled" in result && result.reasoning_disabled) {
        showWarn({ summary: t("rework.admin.capabilities.defaultOffReasoningToast") });
      }
    } catch (error) {
      // The one reachable 409 here is DefaultOnNotAllowed: a capability with a
      // required team setting can never be on by default (#2408). The switch is
      // already disabled for that case, so reaching this branch means a stale
      // client — explain it rather than showing "could not change" (the
      // backend's own sentence is the fallback for anything else).
      const normalized = normalizeApiError(error);
      showError({
        summary: t("rework.admin.capabilities.defaultToggleError"),
        detail:
          !organizationId && normalized.kind === "conflict"
            ? t("rework.admin.capabilities.defaultOnConflict")
            : normalized.detail,
      });
    } finally {
      inFlightDefaultOnIdRef.current = null;
      setTogglingCapabilityId(null);
    }
  };

  const applyReasoning = async (capability: CapabilityEnablementItem, nextValue: boolean) => {
    if (readOnly) return;
    if (inFlightReasoningIdRef.current === capability.id) {
      return;
    }
    inFlightReasoningIdRef.current = capability.id;
    setTogglingReasoningId(capability.id);
    try {
      await setModelReasoning({
        capabilityId: capability.id,
        setModelReasoningRequest: { reasoning_enabled: nextValue },
      }).unwrap();
      showSuccess({
        summary: t(
          nextValue ? "rework.admin.capabilities.reasoningOnToast" : "rework.admin.capabilities.reasoningOffToast",
        ),
      });
    } catch (error) {
      showError({
        summary: t("rework.admin.capabilities.reasoningToggleError"),
        detail: normalizeApiError(error).detail,
      });
    } finally {
      inFlightReasoningIdRef.current = null;
      setTogglingReasoningId(null);
    }
  };

  /**
   * Turn each missing dependency default-on, then the template itself (#2470).
   *
   * Order is load-bearing and matches the backend gate: the template is written
   * LAST, so a dependency that fails leaves "dependency granted, template not"
   * — never the inverse, which is precisely the broken platform-wide state this
   * whole change exists to prevent. There is no transaction available here, so
   * the ordering is the guarantee.
   */
  const grantAllDefaultOn = async (capability: CapabilityEnablementItem) => {
    if (readOnly) return;
    // Re-derived now, not at dialog-open time: the list refetches underneath an
    // open dialog, and re-granting an already-default-on dependency is a wasted
    // write the admin never asked for.
    const missing = missingAgentDependenciesForPlatform(capability, allCapabilities);
    for (const depId of missing) {
      try {
        await setDefaultOn({
          capabilityId: depId,
          setCapabilityDefaultOnRequest: { default_on: true },
        }).unwrap();
      } catch (error) {
        showError({
          summary: t("rework.admin.capabilities.grantAllConfirm.depFailed", {
            dep: dependencyLabels(t, [depId], allCapabilities),
            agent: capabilityLabel(t, capability),
          }),
          detail: normalizeApiError(error).detail,
        });
        return;
      }
    }
    await applyDefaultOn(capability, true);
  };

  const onToggleDefault = (capability: DefaultOnRow) => {
    if (!canToggleDefault(capability)) return;
    if (capability.default_on) {
      // Turning default-on off revokes inherited access team-by-team and can
      // suspend dependent instances — confirm before firing, and preview the
      // platform-wide impact (no teamId) so the admin sees what breaks.
      setPendingDefaultOff(capability);
      setShowAffected(false);
      // Applications have no agent-instance dependencies or suspension
      // lifecycle. Their confirmation stays generic and never asks the
      // agent-specific impact endpoint for a meaningless preview.
      if (isOffer(capability)) {
        if (organizationId) {
          void fetchOfferRevokeImpact({
            organizationId,
            runtimeId: capability.runtime_id,
            capabilityId: capability.capability_id,
          });
        }
      } else if (!discoveringAgents && hasAgentInstanceLifecycle(capability.kind)) {
        void fetchRevokeImpact({ capabilityId: capability.id });
      }
    } else if (
      !isOffer(capability) &&
      !discoveringAgents &&
      missingAgentDependenciesForPlatform(capability, allCapabilities).length > 0
    ) {
      // #2470: the backend now 409s this write. Offer to grant the dependencies
      // in the same gesture rather than surfacing a refusal the admin has to
      // resolve by hand, one capability at a time, elsewhere in the table.
      setPendingGrantAll(capability);
    } else {
      void applyDefaultOn(capability, true);
    }
  };

  // An offer preview lists the instances it would stop; it has no published or unknown count.
  const impactQuery = pendingOffer ? offerRevokeImpact : revokeImpact;
  const impact = revokeImpact.data;
  const offerImpact = offerRevokeImpact.data ?? [];
  const impactSuspended = pendingOffer ? offerImpact.length : (impact?.suspended_instances ?? 0);
  const impactUnknown = pendingOffer ? 0 : (impact?.health_unknown_instances ?? 0);
  const impactPublished = pendingOffer ? 0 : (impact?.published_instances ?? 0);
  const impactInstances = pendingOffer
    ? offerImpact.map((instance) => ({
        id: instance.agent_instance_id,
        name: instance.display_name,
        team: spaceLabel(instance),
      }))
    : (impact?.instances ?? []).map((instance) => ({
        id: instance.agent_instance_id,
        name: instance.display_name,
        // Resolve the opaque Keycloak group id to its team name.
        team: teams.find((team) => team.id === instance.team_id)?.name ?? instance.team_id,
      }));

  // Concrete impact for the disable-confirmation dialog: how many working agents
  // this default-off would suspend, plus the affected-agent drill-down. While
  // the preview is still loading we render nothing extra — the dialog keeps its
  // generic message and stays actionable.
  const renderImpactDetails = () => {
    if (discoveringAgents) return null;
    if (!pendingOffer && !(pendingCapability && hasAgentInstanceLifecycle(pendingCapability.kind))) return null;
    if (impactQuery.isFetching || !impactQuery.data) return null;
    return (
      <div className={styles.impact}>
        <p className={impactSuspended > 0 ? styles.impactWarn : styles.impactNone}>
          {impactSuspended > 0
            ? t("rework.admin.capabilities.defaultOffConfirm.impact", { count: impactSuspended })
            : t("rework.admin.capabilities.defaultOffConfirm.impactNone")}
        </p>
        {impactPublished > 0 && (
          <p className={styles.impactWarn}>
            {t("rework.admin.capabilities.defaultOffConfirm.impactPublished", { count: impactPublished })}
          </p>
        )}
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
                  <li key={instance.id} className={styles.affectedItem}>
                    {t("rework.admin.capabilities.defaultOffConfirm.affectedAgent", {
                      name: instance.name,
                      team: instance.team,
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

  const manageTeamsCell = (dimmed: boolean, disabled: boolean, onClick?: () => void) => (
    <div className={`${styles.actionsCell} ${dimmed ? styles.dimmed : ""}`}>
      <Button
        color="on-surface"
        variant="outlined"
        size="small"
        icon={{ category: "outlined", type: "groups" }}
        onClick={onClick}
        disabled={disabled}
      >
        {t("rework.admin.capabilities.manageTeams")}
      </Button>
    </div>
  );

  const defaultOnCell = (cap: DefaultOnRow) => {
    // §8.2: a capability with a REQUIRED team setting can never be on by
    // default — nobody has filled the settings for the teams that would
    // inherit it, so the write 409s (`DefaultOnNotAllowed`). Turning it
    // OFF stays possible, hence the `!cap.default_on` guard: a row that is
    // already default-on (settings added after the fact) must not be
    // trapped in that state. An offer its pod no longer advertises follows
    // the same rule, without the settings hint.
    //
    // This flips only when `default_on` itself does, i.e. on the
    // turn-OFF path — which runs through the confirmation dialog, so the
    // Switch does not hold focus when the cell re-renders (the dialog
    // restores focus to nothing on close). That is why the swap between
    // the wrapped and bare control cannot reintroduce the Chromium
    // focus-yank bug documented above; it is not because `blockedOn` is
    // constant, which it isn't.
    const blockedOn = !cap.default_on && (isOffer(cap) ? !cap.advertised : requiresTeamSettings(cap));
    const control = (
      <Switch
        size="small"
        checked={cap.default_on}
        disabled={
          !canToggleDefault(cap) ||
          blockedOn ||
          (!isOffer(cap) && unavailableDiscoveredIds.has(cap.id)) ||
          (isTogglingDefault && togglingCapabilityId !== defaultOnKey(cap))
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

  // Shared by catalog rows and pod offers; only catalog rows can be "unknown".
  const healthCell = (suspended: number, unknown: number, onOpen?: () => void) => (
    <div className={styles.centered}>
      {suspended > 0 ? (
        // A button, not a span, so it is keyboard-reachable and announced as actionable.
        <button
          type="button"
          className={styles.healthWarnButton}
          disabled={!onOpen}
          onClick={onOpen}
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
      cellRenderer: (cap) =>
        cap.kind === "model" ? (
          <ModelIdentityCell
            capability={cap}
            dimmed={false}
            unavailable={unavailableDiscoveredIds.has(cap.id)}
            isNew={newModelIds.has(cap.id)}
          />
        ) : (
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
    // Reasoning activation (REASON-01 §5) — a models-only column, so it is
    // absent entirely from the tool/agent views rather than rendered blank.
    // The two axes share this screen and must not be confused: the default-on
    // column above is "who may use this model at all" (ReBAC, per team); this
    // one is "does it run with reasoning" (global, no subject, §5.4).
    ...(activeKindFilter === "model"
      ? [
          {
            label: t("rework.admin.capabilities.col.reasoning"),
            size: "1.1fr",
            cellRenderer: (cap: CapabilityEnablementItem) => {
              // §5.3: no reasoning-capable profile means NO control at all, not
              // a disabled one. Aptitude is declared in models_catalog.yaml —
              // an administrator cannot make a model reason, and a greyed-out
              // switch would suggest the opposite.
              if (!hasReasoningControl(cap)) {
                return <div className={styles.centered} />;
              }
              return (
                <div className={styles.centered}>
                  <Tooltip text={t("rework.admin.capabilities.reasoningHint")}>
                    <Switch
                      size="small"
                      checked={cap.reasoning_enabled ?? false}
                      disabled={
                        readOnly ||
                        unavailableDiscoveredIds.has(cap.id) ||
                        (isTogglingReasoning && togglingReasoningId !== cap.id)
                      }
                      onChange={() => void applyReasoning(cap, !(cap.reasoning_enabled ?? false))}
                      aria-label={t("rework.admin.capabilities.col.reasoning")}
                    />
                  </Tooltip>
                </div>
              );
            },
          },
        ]
      : []),
    {
      label: t("rework.admin.capabilities.col.enabledTeams"),
      size: "1fr",
      cellRenderer: (cap) => {
        const count = enabledTeamCount(cap);
        const personal = hasAgentInstanceLifecycle(cap.kind) ? personalSpaceCount(cap) : 0;
        // Personal spaces have their own denominator; keep separate badges.
        const parts: { icon: "groups" | "person"; value: string; label: string }[] = [];
        if (count !== null && count > 0) {
          parts.push({
            icon: "groups",
            value: String(count),
            label: t("rework.admin.capabilities.enabledTeams.teams", { count }),
          });
        }
        if (personal === null) {
          parts.push({
            icon: "person",
            value: "?",
            label: t("rework.admin.capabilities.enabledTeams.personalUnknown"),
          });
        } else if (personal > 0) {
          parts.push({
            icon: "person",
            value: String(personal),
            label: t("rework.admin.capabilities.enabledTeams.personal", { count: personal }),
          });
        }
        const stack = (
          <span
            className={`${styles.countStack} ${rowIsUnused(cap) && !unavailableDiscoveredIds.has(cap.id) ? styles.dimmed : ""}`}
          >
            {parts.map((part) => (
              <span key={part.icon} className={styles.count} aria-label={part.label} title={part.label}>
                <Icon category="outlined" type={part.icon} />
                {part.value}
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
    ...(!hasAgentInstanceLifecycle(activeKindFilter)
      ? []
      : [
          {
            field: "health" as const,
            label: t("rework.admin.capabilities.col.health"),
            size: activeKindFilter === "model" ? "0.9fr" : "1fr",
            // Resting health from the aggregate list: agents this capability breaks
            // at rest vs. agents whose pod was unreachable, kept visually distinct.
            cellRenderer: (cap: CapabilityEnablementItem) =>
              unavailableDiscoveredIds.has(cap.id) ? (
                <div className={styles.centered}>
                  <span className={styles.healthUnavailable}>
                    {t("rework.admin.capabilities.discovery.unavailable")}
                  </span>
                </div>
              ) : (
                healthCell(
                  cap.suspended_instances ?? 0,
                  cap.health_unknown_instances ?? 0,
                  readOnly ? undefined : () => setSuspendedKey(cap.id),
                )
              ),
          },
        ]),
    {
      field: "actions",
      label: t("rework.admin.capabilities.col.actions"),
      // Keep the icon and label clear of the outline at desktop widths.
      size: "1.55fr",
      // Dimmed but never disabled: an unused capability is exactly the one an
      // admin opens to grant its first team.
      cellRenderer: (cap) =>
        manageTeamsCell(
          rowIsUnused(cap) && !unavailableDiscoveredIds.has(cap.id),
          readOnly || unavailableDiscoveredIds.has(cap.id),
          () => setMatrixCapabilityId(cap.id),
        ),
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
        healthCell(offer.unusable_instances.length, 0, () => setSuspendedKey(defaultOnKey(offer)))
      ) : column.field === "actions" ? (
        manageTeamsCell(!offer.advertised, true)
      ) : (
        <div className={styles.centered} />
      ),
  }));
  const rowCount = discoveringAgents ? agents.length : visibleCapabilities.length;
  const suspendedDrawer = suspendedOffer
    ? {
        name: offerName(suspendedOffer),
        instances: suspendedOffer.unusable_instances.map((instance) => ({
          spaceId: instance.space_id,
          spaceName: spaceLabel(instance),
          displayName: instance.display_name,
        })),
      }
    : suspendedCapability
      ? {
          name: capabilityLabel(t, suspendedCapability),
          instances: (suspendedCapability.suspended_instance_details ?? []).map((instance) => ({
            spaceId: instance.team_id,
            spaceName: teams.find((team) => team.id === instance.team_id)?.name ?? instance.team_id,
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
          activeKindFilter === "model" &&
          (canAdmin || discoveringModels) && (
            <Button
              color="on-surface"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "tune" }}
              disabled={readOnly && !discoveringModels}
              onClick={() => {
                if (readOnly && !discoveringModels) return;
                setModelDefaultsInitialTab("pods");
                setPlatformBindingsPanelOpen(true);
              }}
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
            onSelectedIndexChange={(index) => {
              const next = kindFilters[index];
              if (next === "model") {
                setModelInventoryReady(false);
                setModelSourceCheckReady(false);
                setVerifiedModelSourceIds(null);
                setUnverifiedModelRuntimes([]);
              }
              setKindFilter(next);
              setNoDefaultModalPending(!readOnly && next === "model");
            }}
            items={kindFilters.map((kind) => ({
              label: t(`rework.admin.capabilities.kindFilter.${kind}`),
            }))}
          />
        }
      />

      {discoveringModels && organizationId && (
        <OrganizationModels
          key={organizationId}
          organizationId={organizationId}
          defaultsOpen={platformBindingsPanelOpen}
          onCloseDefaults={() => setPlatformBindingsPanelOpen(false)}
        />
      )}
      {discoveringCapabilities && organizationId && (
        <OrganizationCapabilities
          key={organizationId}
          organizationId={organizationId}
          capabilityColumns={offerColumns}
        />
      )}

      {isLoading && <p className={styles.status}>{t("rework.admin.capabilities.loading")}</p>}
      {isError && <p className={styles.statusError}>{t("rework.admin.capabilities.loadError")}</p>}
      {legacyModels && !discoveryConfigurationReady && !isLoading && !isError && (
        <p className={styles.status}>{t("rework.admin.capabilities.discovery.refreshing")}</p>
      )}

      {legacyModels && hasDiscovery && (
        <div className={styles.modelToolbar}>
          <ButtonGroup
            size="2xs"
            color="secondary"
            variant="radio"
            aria-label={t("rework.admin.capabilities.discovery.tabAria")}
            selectedIndex={modelTab === "manual" ? 0 : 1}
            onSelectedIndexChange={(index) => setModelTab(index === 0 ? "manual" : "discovered")}
            items={[
              { label: t("rework.admin.capabilities.discovery.manualSection") },
              { label: t("rework.admin.capabilities.discovery.discoveredSection") },
            ]}
          />
        </div>
      )}

      {legacyModels && hasDiscovery && modelTab === "discovered" && (
        <ModelDiscoveryStatus
          data={discoveryStatus ? { ...discoveryStatus, sources: discoverySources } : undefined}
          discoveredSourceIds={discoveredModels.flatMap((model) =>
            model.model_discovery_source_id ? [model.model_discovery_source_id] : [],
          )}
          refreshing={discoveryRefresh.isLoading || !modelInventoryReady}
          refreshError={discoveryRefresh.isError || Boolean(modelRefreshError)}
          refreshErrorMessage={modelRefreshError}
          unverifiedRuntimes={currentUnverifiedRuntimes}
          verifiedSourceIds={currentVerifiedSourceIds ?? []}
        />
      )}

      {legacyModels && discoveryConfigurationReady && !hasDiscovery && (
        <UnverifiedRuntimeWarning runtimes={currentUnverifiedRuntimes} />
      )}

      {!organizationPanel &&
        !isLoading &&
        !isError &&
        (activeKindFilter !== "model" || discoveryConfigurationReady) &&
        rowCount === 0 &&
        !(legacyModels && hasDiscovery) && (
          <PageEmptyState
            icon="tune"
            message={t(
              activeKindFilter === "agent"
                ? "rework.admin.capabilities.emptyAgents"
                : activeKindFilter === "model"
                  ? "rework.admin.capabilities.emptyModels"
                  : activeKindFilter === "app"
                    ? "rework.admin.capabilities.emptyApps"
                    : activeKindFilter === "knowledge_base"
                      ? "rework.admin.capabilities.emptyKnowledgeBases"
                      : "rework.admin.capabilities.empty",
            )}
          />
        )}

      {!organizationPanel &&
        !isLoading &&
        !isError &&
        (activeKindFilter !== "model" || discoveryConfigurationReady) &&
        (rowCount > 0 || (legacyModels && hasDiscovery)) &&
        (discoveringAgents ? (
          <DataTable columns={discoveryColumns} data={agents} size="medium" />
        ) : legacyModels && hasDiscovery ? (
          <section
            className={styles.modelSection}
            aria-label={t(`rework.admin.capabilities.discovery.${modelTab}Section`)}
          >
            <div className={styles.modelListToolbar}>
              {modelTab === "discovered" && (
                <Button
                  color="on-surface"
                  variant="outlined"
                  size="small"
                  icon={{ category: "outlined", type: "refresh" }}
                  disabled={discoveryRefresh.isLoading || !modelInventoryReady}
                  onClick={() => void refreshModels()}
                >
                  {t("rework.admin.capabilities.discovery.refresh")}
                </Button>
              )}
              <div className={styles.modelFilter}>
                <SearchInput
                  size="small"
                  ariaLabel={t("rework.admin.capabilities.discovery.filter")}
                  clearAriaLabel={t("rework.admin.capabilities.discovery.clearFilter")}
                  placeholder={t("rework.admin.capabilities.discovery.filter")}
                  value={modelFilter}
                  onChange={setModelFilter}
                />
              </div>
            </div>
            {visibleModels.length === 0 ? (
              <p className={styles.status}>
                {t(
                  modelFilter
                    ? "rework.admin.capabilities.discovery.noMatches"
                    : `rework.admin.capabilities.discovery.empty${modelTab === "manual" ? "Manual" : "Discovered"}`,
                )}
              </p>
            ) : (
              <DataTable
                columns={columns}
                data={visibleModels}
                rowKey={(capability) => capability.id}
                rowClassName={(capability) =>
                  unavailableDiscoveredIds.has(capability.id) ? styles.unavailableRow : undefined
                }
                size="medium"
              />
            )}
          </section>
        ) : (
          <DataTable
            columns={columns}
            data={visibleCapabilities}
            rowKey={(capability) => capability.id}
            size="medium"
          />
        ))}

      <ConfirmationDialog
        open={visiblePendingDefaultOff !== null}
        title={t(`rework.admin.capabilities.defaultOffConfirm.${defaultOffCopyVariant}Title`)}
        message={t(`rework.admin.capabilities.defaultOffConfirm.${defaultOffCopyVariant}Message`)}
        details={renderImpactDetails()}
        confirmLabel={t("rework.admin.capabilities.defaultOffConfirm.confirm")}
        cancelLabel={t("rework.admin.capabilities.defaultOffConfirm.cancel")}
        criticalAction
        onConfirm={() => {
          if (visiblePendingDefaultOff) void applyDefaultOn(visiblePendingDefaultOff, false);
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
      {!readOnly && (
        <>
          <CapabilityTeamMatrixDrawer
            capability={matrixCapability}
            unavailable={matrixCapability !== null && unavailableDiscoveredIds.has(matrixCapability.id)}
            // The FULL catalog, not the kind-filtered `capabilities`: an agent's
            // dependencies are tool rows the Agents tab has filtered out (#2408).
            allCapabilities={allCapabilities}
            teams={teams}
            teamsLoading={isTeamsLoading}
            teamsError={isTeamsError}
            open={matrixCapability !== null}
            onClose={() => setMatrixCapabilityId(null)}
          />

          <PlatformModelBindingsPanel
            open={platformBindingsPanelOpen}
            onClose={() => setPlatformBindingsPanelOpen(false)}
            initialTab={modelDefaultsInitialTab}
          />

          <ConfirmationDialog
            open={noDefaultModalOpen}
            title={t("rework.admin.platformModelBindings.noPlatformDefaultTitle")}
            message={t("rework.admin.platformModelBindings.noPlatformDefault")}
            confirmLabel={t("rework.admin.platformModelBindings.chooseModel")}
            showCancel={false}
            dismissible={false}
            onConfirm={() => {
              setNoDefaultModalOpen(false);
              setModelDefaultsInitialTab("pods");
              setPlatformBindingsPanelOpen(true);
            }}
            onCancel={() => setNoDefaultModalOpen(false)}
          />

          <ConfirmationDialog
            open={pendingGrantAll !== null}
            title={t("rework.admin.capabilities.grantAllConfirm.title")}
            message={
              pendingGrantAll
                ? t("rework.admin.capabilities.grantAllConfirm.messagePlatform", {
                    agent: capabilityLabel(t, pendingGrantAll),
                    deps: dependencyLabels(
                      t,
                      missingAgentDependenciesForPlatform(pendingGrantAll, allCapabilities),
                      allCapabilities,
                    ),
                  })
                : ""
            }
            confirmLabel={t("rework.admin.capabilities.grantAllConfirm.confirm")}
            cancelLabel={t("rework.admin.capabilities.grantAllConfirm.cancel")}
            onConfirm={() => {
              if (pendingGrantAll) void grantAllDefaultOn(pendingGrantAll);
              setPendingGrantAll(null);
            }}
            onCancel={() => setPendingGrantAll(null)}
          />
        </>
      )}
    </div>
  );
}
