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

import Button from "@shared/atoms/Button/Button.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import AgentCard, { type AgentCardMarketplace } from "@shared/organisms/AgentCard/AgentCard.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import {
  useDismissAgentMarketplaceRemovalMutation,
  useGetTeamQuery,
  usePublishAgentMutation,
  useUnpublishAgentMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { type AgentFormPayload, default as AgentFormModal } from "./AgentFormModal/AgentFormModal.tsx";
import CopyAgentDialog from "./CopyAgentDialog/CopyAgentDialog.tsx";
import { duplicateCopyArgs, duplicateWarning } from "./duplicateAgent.ts";
import DuplicateAgentDialog from "./DuplicateAgentDialog/DuplicateAgentDialog.tsx";
import TeamAgentEmptyState from "./TeamAgentEmptyState/TeamAgentEmptyState.tsx";
import PublishAgentDialog from "./PublishAgentDialog/PublishAgentDialog.tsx";
import RepublishProposalDialog, {
  type RepublishProposalCause,
} from "./RepublishProposalDialog/RepublishProposalDialog.tsx";
import {
  agentFileCapabilities,
  isPublished,
  marketplaceErrorView,
  publishAvailability,
  publishBlockedText,
  teamCanPublish,
} from "./agentMarketplace.ts";
import { filterAgents } from "./agentFilter.ts";
import {
  AGENT_NAME_CONFLICT,
  freeAgentName,
  isAgentNameConflict,
  normalizeAgentName,
  takenAgentNames,
} from "./agentNames.ts";
import { getStoredAgentSort, sortAgents, storeAgentSort, type AgentSortValue } from "./agentSort.ts";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { useUsersByIdsQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  type CreateAgentInstanceRequest,
  type ManagedAgentInstanceSummary,
  type UpdateAgentInstanceRequest,
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation,
  usePatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchMutation,
  usePostAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPostMutation,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
  usePostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamAgentsPage.module.css";

type AgentRequestTuningFieldValues = NonNullable<CreateAgentInstanceRequest["tuning_field_values"]>;
type AgentRequestCapabilityConfigValues = NonNullable<CreateAgentInstanceRequest["capability_config_values"]>;

/**
 * Build the multipart body of the `with-assets` save endpoints (#1903): the
 * JSON request as a `request` form field plus one `{capabilityId}:{slotKey}`
 * reference per file, aligned by index with the `asset_files` entries. The
 * generated client cannot express multipart, so the FormData is passed as the
 * generated mutation's body — the sanctioned narrow exception (the TYPES still
 * come from the generated client; see CLAUDE.md backend↔frontend contract).
 */
function buildAgentSaveFormData(
  request: CreateAgentInstanceRequest | UpdateAgentInstanceRequest,
  assetFiles: Record<string, Record<string, File>>,
): FormData {
  const formData = new FormData();
  formData.append("request", JSON.stringify(request));
  for (const [capabilityId, slots] of Object.entries(assetFiles)) {
    for (const [slotKey, file] of Object.entries(slots)) {
      formData.append("asset_slots", `${capabilityId}:${slotKey}`);
      formData.append("asset_files", file, file.name);
    }
  }
  return formData;
}

const hasAssetFiles = (assetFiles: Record<string, Record<string, File>>): boolean =>
  Object.values(assetFiles).some((slots) => Object.keys(slots).length > 0);

/** Returns undefined (rather than a hardcoded fallback string) when no usable
 *  detail is found — callers supply their own translated fallback. */
function extractApiErrorDetail(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null) return String(error);
  const data = (error as Record<string, unknown>).data;
  if (typeof data === "object" && data !== null) {
    const detail = (data as Record<string, unknown>).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e) =>
          typeof e === "object" && e !== null
            ? String((e as Record<string, unknown>).msg ?? JSON.stringify(e))
            : String(e),
        )
        .join("; ");
    }
  }
  const msg = (error as Record<string, unknown>).message;
  return typeof msg === "string" ? msg : undefined;
}

/**
 * Lists the managed agent instances for the current team and exposes
 * create / edit / delete operations for team admins.
 *
 * Chat is a dedicated button inside `AgentCard` (#2076), not a whole-card
 * click — `AgentCard` builds its own managed-chat link from `teamId`.
 */
export default function TeamAgentsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const { showError, showSuccess, showWarn } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { activeTeam } = useFrontendBootstrap();
  const { agentsNicknamePlural, agentsNicknameSingular } = useFrontendProperties();

  const isPersonalTeam = teamId === activeTeam?.id;
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);
  const [editingInstance, setEditingInstance] = useState<ManagedAgentInstanceSummary | null>(null);
  const [duplicatingInstance, setDuplicatingInstance] = useState<ManagedAgentInstanceSummary | null>(null);
  // Chosen when the dialog opens, so a later refresh of the list never
  // replaces what the person is typing.
  const [duplicateName, setDuplicateName] = useState("");
  // Names the server refused as taken but the loaded list does not show yet
  // (taken in the meantime); kept so the form marks its name field.
  const [refusedNames, setRefusedNames] = useState<ReadonlySet<string>>(new Set());
  const [copyingInstance, setCopyingInstance] = useState<ManagedAgentInstanceSummary | null>(null);
  const [publishingInstance, setPublishingInstance] = useState<ManagedAgentInstanceSummary | null>(null);
  const [proposal, setProposal] = useState<{
    instance: ManagedAgentInstanceSummary;
    cause: RepublishProposalCause;
  } | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<AgentSortValue>(getStoredAgentSort);
  const changeSort = (next: AgentSortValue) => {
    setSort(next);
    storeAgentSort(next);
  };

  const { data: fetchedTeam } = useGetTeamQuery({ teamId: teamId || "" }, { skip: !teamId || isPersonalTeam });
  const team = isPersonalTeam ? activeTeam : fetchedTeam;
  const {
    canUpdateAgents: canManageAgents,
    canPublishMarketplaceAgents: canPublish,
    canUnpublishMarketplaceAgents: canUnpublish,
  } = useTeamCapabilities(team);

  const {
    data: managedInstances = [],
    isLoading: isLoadingInstances,
    isError: isInstancesError,
    refetch: refetchInstances,
  } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId: teamId || "" },
    { skip: !teamId },
  );

  const {
    data: availableTemplates = [],
    isLoading: isLoadingTemplates,
    isError: isTemplatesError,
  } = useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery(
    { teamId: teamId || "" },
    { skip: !teamId || !canManageAgents },
  );

  // Must stay above the early returns below - a hook after them renders a
  // different hook count when a query errors, which React refuses.
  // A suspended agent stays hidden from chat-only members (they cannot fix it
  // and must not see a broken agent); editors/owners keep seeing it with a
  // warning and a locked enable toggle. The search narrows what is left.
  const searchedInstances = useMemo(
    () =>
      sortAgents(
        filterAgents(
          managedInstances.filter((instance) => canManageAgents || !instance.suspension_reason),
          search,
        ),
        sort,
      ),
    [managedInstances, canManageAgents, search, sort],
  );

  // Batched once for the whole list (not one query per card, #2096) — the
  // agent card's info tooltip shows created_by/updated_by display names.
  const auditUids = Array.from(
    new Set(
      managedInstances
        .flatMap((instance) => [instance.created_by, instance.updated_by])
        .filter((uid): uid is string => Boolean(uid)),
    ),
  );
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });
  const auditUserById = new Map(auditUsers.map((summary) => [summary.id, summary]));

  const [copyAgent, { isLoading: isCopyingInstance }] =
    usePostAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPostMutation();
  const [createManagedInstance, { isLoading: isCreatingInstance }] =
    usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation();
  const [createManagedInstanceWithAssets, { isLoading: isCreatingInstanceWithAssets }] =
    usePostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostMutation();
  const [patchManagedInstance, { isLoading: isUpdatingInstance }] =
    usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation();
  const [patchManagedInstanceWithAssets, { isLoading: isUpdatingInstanceWithAssets }] =
    usePatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchMutation();
  const [deleteManagedInstance] =
    useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation();
  const [publishAgent, { isLoading: isPublishing }] = usePublishAgentMutation();
  const [unpublishAgent] = useUnpublishAgentMutation();
  const [dismissRemoval] = useDismissAgentMarketplaceRemovalMutation();

  const availabilityOf = (instance: ManagedAgentInstanceSummary) =>
    publishAvailability({
      instance,
      team,
      canPublish,
      isPersonalTeam,
      templates: isTemplatesError ? undefined : availableTemplates,
    });
  const capabilityName = (capabilityId: string) => {
    const capability = availableTemplates
      .flatMap((tpl) => tpl.available_capabilities ?? [])
      .find((entry) => entry.id === capabilityId);
    return capability ? t(capability.name, { defaultValue: capabilityId }) : capabilityId;
  };
  const showMarketplaceError = (summaryKey: string, error: unknown) => {
    const view = marketplaceErrorView(error, t, capabilityName);
    if (view.stale) void refetchInstances();
    showError({ summary: t(summaryKey), detail: view.message });
  };

  // After an editor's own save or reactivation, offer to republish; the
  // refreshed row says whether the save actually changed the agent.
  const proposeRepublish = (instance: ManagedAgentInstanceSummary | undefined, cause: RepublishProposalCause) => {
    if (!instance || !availabilityOf(instance)) return;
    const shouldPropose =
      cause === "saved"
        ? isPublished(instance) && !!instance.marketplace?.modified
        : instance.marketplace?.state === "removed" && instance.marketplace.removed_reason === "deactivated";
    if (shouldPropose) setProposal({ instance, cause });
  };

  const handlePublish = async (instance: ManagedAgentInstanceSummary) => {
    if (!teamId) return;
    try {
      await publishAgent({
        teamId,
        agentInstanceId: instance.agent_instance_id,
        publishAgentRequest: { expected_version: instance.marketplace?.version ?? null },
      }).unwrap();
      showSuccess({ summary: t("rework.agentMarketplace.publishSuccess", { name: instance.display_name }) });
      setPublishingInstance(null);
    } catch (error: unknown) {
      setPublishingInstance(null);
      showMarketplaceError("rework.agentMarketplace.publishError", error);
    }
  };

  const handleRemove = (instance: ManagedAgentInstanceSummary) => {
    if (!teamId || !instance.marketplace) return;
    const expectedVersion = instance.marketplace.version;
    showConfirmationDialog({
      title: t("rework.agentMarketplace.removeDialog.title"),
      message: t("rework.agentMarketplace.removeDialog.message", { name: instance.display_name }),
      confirmButtonLabel: t("rework.agentMarketplace.removeDialog.confirm"),
      cancelButtonLabel: t("rework.agentCard.deleteDialog.cancel"),
      onConfirm: async () => {
        try {
          await unpublishAgent({
            teamId,
            agentInstanceId: instance.agent_instance_id,
            unpublishAgentRequest: { expected_version: expectedVersion },
          }).unwrap();
          showSuccess({ summary: t("rework.agentMarketplace.removeSuccess", { name: instance.display_name }) });
        } catch (error: unknown) {
          showMarketplaceError("rework.agentMarketplace.removeError", error);
        }
      },
    });
  };

  const handleHideRemoval = async (instance: ManagedAgentInstanceSummary) => {
    if (!teamId) return;
    try {
      await dismissRemoval({ teamId, agentInstanceId: instance.agent_instance_id }).unwrap();
    } catch (error: unknown) {
      showMarketplaceError("rework.agentMarketplace.hideError", error);
    }
  };

  const takenNames = useMemo(
    () => new Set([...takenAgentNames(managedInstances, editingInstance?.agent_instance_id), ...refusedNames]),
    [managedInstances, editingInstance, refusedNames],
  );
  const duplicateTakenNames = useMemo(
    () => new Set([...takenAgentNames(managedInstances), ...refusedNames]),
    [managedInstances, refusedNames],
  );
  const refuseName = (name: string) => {
    setRefusedNames((prev) => new Set([...prev, normalizeAgentName(name)]));
    void refetchInstances();
  };

  const handleEnroll = async (payload: AgentFormPayload) => {
    if (!teamId) return;
    const request: CreateAgentInstanceRequest = {
      template_id: payload.templateId,
      display_name: payload.displayName,
      role: payload.role || undefined,
      description: payload.description || undefined,
      usage_statement: payload.usageStatement,
      reasoning_enabled: payload.reasoningEnabled,
      reasoning_default_on: payload.reasoningDefaultOn,
      tuning_field_values:
        Object.keys(payload.tuningFieldValues).length > 0
          ? (payload.tuningFieldValues as AgentRequestTuningFieldValues)
          : undefined,
      capability_ids: payload.templateHasCapabilities ? payload.selectedCapabilityIds : undefined,
      capability_config_values:
        payload.templateHasCapabilities && Object.keys(payload.capabilityConfigValues).length > 0
          ? (payload.capabilityConfigValues as AgentRequestCapabilityConfigValues)
          : undefined,
    };
    try {
      if (hasAssetFiles(payload.capabilityAssetFiles)) {
        // Capability asset uploads travel INSIDE the atomic save (#1903): the
        // multipart companion endpoint relays them to the pod's validate-config.
        await createManagedInstanceWithAssets({
          teamId,
          bodyPostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPost:
            buildAgentSaveFormData(request, payload.capabilityAssetFiles) as unknown as {
              request: string;
            },
        }).unwrap();
      } else {
        await createManagedInstance({ teamId, createAgentInstanceRequest: request }).unwrap();
      }
      showSuccess({ summary: t("rework.agentCard.createSuccess", { agent: agentsNicknameSingular }) });
      setIsEnrollOpen(false);
      await refetchInstances();
    } catch (error: unknown) {
      if (isAgentNameConflict(error)) {
        refuseName(request.display_name);
        return;
      }
      showError({
        summary: t("rework.agentCard.createError", { agent: agentsNicknameSingular.toLowerCase() }),
        detail: extractApiErrorDetail(error) ?? t("rework.agentCard.unexpectedError"),
      });
    }
  };

  const handleEdit = async (payload: AgentFormPayload) => {
    if (!teamId || !editingInstance) return;
    const edited = editingInstance;
    const request: UpdateAgentInstanceRequest = {
      display_name: payload.displayName,
      role: payload.role || undefined,
      description: payload.description || undefined,
      usage_statement: payload.usageStatement,
      reasoning_enabled: payload.reasoningEnabled,
      reasoning_default_on: payload.reasoningDefaultOn,
      tuning_field_values:
        Object.keys(payload.tuningFieldValues).length > 0
          ? (payload.tuningFieldValues as AgentRequestTuningFieldValues)
          : undefined,
      capability_ids: payload.templateHasCapabilities ? payload.selectedCapabilityIds : undefined,
      capability_config_values:
        payload.templateHasCapabilities && Object.keys(payload.capabilityConfigValues).length > 0
          ? (payload.capabilityConfigValues as AgentRequestCapabilityConfigValues)
          : undefined,
    };
    try {
      if (hasAssetFiles(payload.capabilityAssetFiles)) {
        await patchManagedInstanceWithAssets({
          teamId,
          agentInstanceId: editingInstance.agent_instance_id,
          bodyPatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatch:
            buildAgentSaveFormData(request, payload.capabilityAssetFiles) as unknown as {
              request: string;
            },
        }).unwrap();
      } else {
        await patchManagedInstance({
          teamId,
          agentInstanceId: editingInstance.agent_instance_id,
          updateAgentInstanceRequest: request,
        }).unwrap();
      }
      showSuccess({ summary: t("rework.agentCard.updateSuccess", { agent: agentsNicknameSingular }) });
      setEditingInstance(null);
      const { data: refreshed } = await refetchInstances();
      if (isPublished(edited)) {
        proposeRepublish(
          refreshed?.find((item) => item.agent_instance_id === edited.agent_instance_id),
          "saved",
        );
      }
    } catch (error: unknown) {
      if (isAgentNameConflict(error) && request.display_name) {
        refuseName(request.display_name);
        return;
      }
      showError({
        summary: t("rework.agentCard.updateError", { agent: agentsNicknameSingular.toLowerCase() }),
        detail: extractApiErrorDetail(error) ?? t("rework.agentCard.unexpectedError"),
      });
    }
  };

  const handleToggleEnabled = (instance: ManagedAgentInstanceSummary) => {
    if (instance.status === "enabled" && isPublished(instance)) {
      showConfirmationDialog({
        criticalAction: true,
        title: t("rework.agentMarketplace.deactivateDialog.title"),
        message: t("rework.agentMarketplace.deactivateDialog.message", { name: instance.display_name }),
        confirmButtonLabel: t("rework.agentMarketplace.deactivateDialog.confirm"),
        cancelButtonLabel: t("rework.agentCard.deleteDialog.cancel"),
        onConfirm: () => void applyToggleEnabled(instance),
      });
      return;
    }
    void applyToggleEnabled(instance);
  };

  const applyToggleEnabled = async (instance: ManagedAgentInstanceSummary) => {
    if (!teamId) return;
    const newStatus = instance.status === "enabled" ? "disabled" : "enabled";
    try {
      await patchManagedInstance({
        teamId,
        agentInstanceId: instance.agent_instance_id,
        updateAgentInstanceRequest: { status: newStatus },
      }).unwrap();
      const statusLabel = t(
        newStatus === "enabled" ? "rework.agentCard.statusEnabled" : "rework.agentCard.statusDisabled",
      );
      showSuccess({
        summary: t("rework.agentCard.toggleSuccess", { agent: agentsNicknameSingular, status: statusLabel }),
      });
      await refetchInstances();
      if (newStatus === "enabled") proposeRepublish(instance, "reactivated");
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: t("rework.agentCard.updateError", { agent: agentsNicknameSingular.toLowerCase() }),
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  const handleDuplicate = async (source: ManagedAgentInstanceSummary, newName: string) => {
    if (!teamId) return;
    try {
      const { results } = await copyAgent(duplicateCopyArgs(source, teamId, newName)).unwrap();
      const [result] = results;
      if (result?.error_code === AGENT_NAME_CONFLICT) {
        refuseName(newName);
        return;
      }
      if (!result?.agent) throw new Error(result?.error ?? t("rework.agentCard.unexpectedError"));
      showSuccess({ summary: t("rework.agentCard.duplicateSuccess", { agent: agentsNicknameSingular }) });
      // Never lose a capability silently: say what was left out or must be redone.
      const warning = duplicateWarning(result, t);
      if (warning) showWarn({ summary: t("rework.agentCard.copyDialog.noticesToast"), detail: warning });
      setDuplicatingInstance(null);
      await refetchInstances();
    } catch (error: unknown) {
      showError({
        summary: t("rework.agentCard.duplicateError", { agent: agentsNicknameSingular.toLowerCase() }),
        detail: extractApiErrorDetail(error) ?? t("rework.agentCard.unexpectedError"),
      });
    }
  };

  const handleDelete = (instance: ManagedAgentInstanceSummary) => {
    if (!teamId) return;
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.agentCard.deleteDialog.title"),
      message: isPublished(instance)
        ? `${t("rework.agentCard.deleteDialog.message", { name: instance.display_name })} ${t(
            "rework.agentMarketplace.deleteRemoves",
          )}`
        : t("rework.agentCard.deleteDialog.message", { name: instance.display_name }),
      confirmButtonLabel: t("rework.agentCard.deleteDialog.confirm"),
      cancelButtonLabel: t("rework.agentCard.deleteDialog.cancel"),
      onConfirm: async () => {
        try {
          await deleteManagedInstance({
            teamId,
            agentInstanceId: instance.agent_instance_id,
          }).unwrap();
          showSuccess({ summary: t("rework.agentCard.deleteSuccess", { agent: agentsNicknameSingular }) });
          setEditingInstance(null);
          await refetchInstances();
        } catch (error: unknown) {
          const err = error as { data?: { detail?: string }; message?: string };
          showError({
            summary: t("rework.agentCard.deleteError", { agent: agentsNicknameSingular.toLowerCase() }),
            detail: err?.data?.detail || err?.message || String(error),
          });
        }
      },
    });
  };

  const showMarketplaceBar = teamCanPublish(team, isPersonalTeam);
  const cardMarketplace = (instance: ManagedAgentInstanceSummary): AgentCardMarketplace | undefined => {
    if (isPersonalTeam) return undefined;
    const availability = availabilityOf(instance);
    return {
      showBar: showMarketplaceBar,
      publishAction: availability
        ? {
            kind: availability.kind,
            disabledReason: availability.blockedReason ? publishBlockedText(availability.blockedReason, t) : undefined,
          }
        : undefined,
      canRemove: canUnpublish && isPublished(instance),
      showDetailedState: canManageAgents || canUnpublish,
      canHide: canUnpublish,
      onPublish: () => setPublishingInstance(instance),
      onRemove: () => handleRemove(instance),
      onHide: () => void handleHideRemoval(instance),
    };
  };

  if (!teamId) {
    return <div className={styles.pageError}>{t("rework.agentCard.missingTeamId")}</div>;
  }

  const isControlPlaneUnavailable =
    !isLoadingInstances && (isInstancesError || (canManageAgents && !isLoadingTemplates && isTemplatesError));

  if (isControlPlaneUnavailable) {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.controlPlane.title")}
        description={t("rework.serviceNotice.controlPlane.description")}
        centered
      />
    );
  }

  const templatesUnavailable =
    canManageAgents && !isLoadingTemplates && !isTemplatesError && availableTemplates.length === 0;
  const showEmptyState = !isLoadingInstances && managedInstances.length === 0;
  const hasAgents = managedInstances.length > 0;
  const sortOptions: OptionModel<AgentSortValue>[] = [
    { value: "name", key: "name", label: t("rework.teams.agents.sort.name") },
    { value: "created_at:desc", key: "created", label: t("rework.teams.agents.sort.created") },
    { value: "updated_at:desc", key: "updated", label: t("rework.teams.agents.sort.updated") },
  ];
  // Only a non-empty query earns the no-match message: an empty list under an
  // empty query means something else entirely, and is left as it was.
  const showNoSearchMatch = Boolean(search.trim()) && searchedInstances.length === 0;
  const teamMarketplace = isPersonalTeam ? null : team?.marketplace;
  const proposalAvailability = proposal ? availabilityOf(proposal.instance) : null;

  return (
    <div className={styles.teamAgentContainer}>
      {hasAgents && !templatesUnavailable && (
        <div className={styles.title}>
          <PageHeader
            title={isPersonalTeam ? t("rework.teams.agents.titlePersonal") : t("rework.teams.agents.title")}
            actions={
              <>
                {canManageAgents && (
                  <Button
                    color={"primary"}
                    variant={"filled"}
                    size={"small"}
                    icon={{ category: "outlined", type: "add" }}
                    onClick={() => setIsEnrollOpen(true)}
                  >
                    {t("rework.teams.agents.create", { agentsNicknameSingular })}
                  </Button>
                )}
                <div className={styles.searchBar}>
                  <SearchInput
                    value={search}
                    onChange={setSearch}
                    placeholder={t("rework.teams.agents.searchPlaceholder", {
                      agentsNicknamePlural: agentsNicknamePlural.toLowerCase(),
                    })}
                    clearAriaLabel={t("rework.teams.agents.clearSearch")}
                    size="xs"
                  />
                </div>
                <div className={styles.sortSelect}>
                  <Select<AgentSortValue>
                    size="xs"
                    compact
                    options={sortOptions}
                    value={sort}
                    onChange={changeSort}
                    ariaLabel={t("rework.teams.agents.sortLabel")}
                  />
                </div>
              </>
            }
          />
        </div>
      )}

      {isLoadingInstances ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
          {t("rework.teams.agents.loading", { agentsNicknamePlural: agentsNicknamePlural.toLowerCase() })}
        </div>
      ) : templatesUnavailable ? (
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.serviceNotice.agentTemplates.title")}
          description={t("rework.serviceNotice.agentTemplates.description")}
          centered
        />
      ) : showEmptyState ? (
        <TeamAgentEmptyState
          canManageAgents={canManageAgents}
          templatesUnavailable={false}
          onCreateAgent={() => setIsEnrollOpen(true)}
        />
      ) : showNoSearchMatch ? (
        <div className={styles.emptySearch}>{t("rework.teams.agents.emptySearch")}</div>
      ) : (
        <div className={styles.agentListScroll}>
          <div className={styles.agentList}>
            {searchedInstances.map((instance) => {
              const template = availableTemplates.find((tpl) => tpl.template_id === instance.template_id);
              return (
                <AgentCard
                  key={instance.agent_instance_id}
                  instance={instance}
                  templateDisplayName={template?.display_name || instance.template_id}
                  runtimeId={template?.source_runtime_id}
                  teamId={teamId}
                  canManageAgents={canManageAgents}
                  offline={templatesUnavailable}
                  auditUserById={auditUserById}
                  onEdit={() => setEditingInstance(instance)}
                  onToggleEnabled={() => handleToggleEnabled(instance)}
                  onDuplicate={() => {
                    setDuplicateName(
                      freeAgentName(
                        instance.display_name,
                        duplicateTakenNames,
                        t("rework.agentCard.duplicateDialog.copyWord"),
                      ),
                    );
                    setDuplicatingInstance(instance);
                  }}
                  onCopyTo={() => setCopyingInstance(instance)}
                  onDelete={() => handleDelete(instance)}
                  marketplace={cardMarketplace(instance)}
                />
              );
            })}
          </div>
        </div>
      )}

      <AgentFormModal
        isOpen={isEnrollOpen || editingInstance !== null}
        isSubmitting={
          isCreatingInstance || isUpdatingInstance || isCreatingInstanceWithAssets || isUpdatingInstanceWithAssets
        }
        mode={editingInstance ? "edit" : "create"}
        editInstance={editingInstance ?? undefined}
        // Personal team's backend name is a non-localized literal ("Equipe
        // personnelle"); pass undefined so the modal falls back to the localized
        // "Personal space" label (follows the user's profile language).
        teamName={isPersonalTeam ? undefined : team?.name}
        teamId={teamId}
        templates={availableTemplates}
        onClose={() => {
          setIsEnrollOpen(false);
          setEditingInstance(null);
        }}
        onSubmit={editingInstance ? handleEdit : handleEnroll}
        onDelete={editingInstance ? () => handleDelete(editingInstance) : undefined}
        takenNames={takenNames}
      />

      <DuplicateAgentDialog
        open={duplicatingInstance !== null}
        initialName={duplicateName}
        isSubmitting={isCopyingInstance}
        takenNames={duplicateTakenNames}
        onCancel={() => setDuplicatingInstance(null)}
        onConfirm={(newName) => {
          if (duplicatingInstance) void handleDuplicate(duplicatingInstance, newName);
        }}
      />

      <CopyAgentDialog instance={copyingInstance} onClose={() => setCopyingInstance(null)} />

      <PublishAgentDialog
        open={publishingInstance !== null}
        agentName={publishingInstance?.display_name ?? ""}
        republish={publishingInstance ? isPublished(publishingInstance) : false}
        fileNames={publishingInstance ? agentFileCapabilities(publishingInstance, availableTemplates, t) : []}
        publishedCount={teamMarketplace?.published_count}
        quota={teamMarketplace?.agents_publish_quota}
        isSubmitting={isPublishing}
        onCancel={() => setPublishingInstance(null)}
        onConfirm={() => {
          if (publishingInstance) void handlePublish(publishingInstance);
        }}
      />

      <RepublishProposalDialog
        open={proposal !== null}
        agentName={proposal?.instance.display_name ?? ""}
        cause={proposal?.cause ?? "saved"}
        blockedReason={
          proposalAvailability?.blockedReason ? publishBlockedText(proposalAvailability.blockedReason, t) : undefined
        }
        onPublish={() => {
          if (proposal) setPublishingInstance(proposal.instance);
          setProposal(null);
        }}
        onIgnore={() => setProposal(null)}
      />
    </div>
  );
}
