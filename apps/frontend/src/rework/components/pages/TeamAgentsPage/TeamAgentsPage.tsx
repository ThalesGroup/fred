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
import AgentCard from "@shared/organisms/AgentCard/AgentCard.tsx";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import {
  type AgentFormPayload,
  buildAgentFormSubmitPayload,
  extractCapabilityConfigValues,
  default as AgentFormModal,
} from "./AgentFormModal/AgentFormModal.tsx";
import DuplicateAgentDialog from "./DuplicateAgentDialog/DuplicateAgentDialog.tsx";
import TeamAgentEmptyState from "./TeamAgentEmptyState/TeamAgentEmptyState.tsx";
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
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { activeTeam } = useFrontendBootstrap();
  const { agentsNicknamePlural, agentsNicknameSingular } = useFrontendProperties();

  const isPersonalTeam = teamId === activeTeam?.id;
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);
  const [editingInstance, setEditingInstance] = useState<ManagedAgentInstanceSummary | null>(null);
  const [duplicatingInstance, setDuplicatingInstance] = useState<ManagedAgentInstanceSummary | null>(null);

  const { data: fetchedTeam } = useGetTeamQuery({ teamId: teamId || "" }, { skip: !teamId || isPersonalTeam });
  const team = isPersonalTeam ? activeTeam : fetchedTeam;
  const { canUpdateAgents: canManageAgents } = useTeamCapabilities(team);

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

  const handleEnroll = async (payload: AgentFormPayload) => {
    if (!teamId) return;
    const request: CreateAgentInstanceRequest = {
      template_id: payload.templateId,
      display_name: payload.displayName,
      role: payload.role || undefined,
      description: payload.description || undefined,
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
      showError({
        summary: t("rework.agentCard.createError", { agent: agentsNicknameSingular.toLowerCase() }),
        detail: extractApiErrorDetail(error) ?? t("rework.agentCard.unexpectedError"),
      });
    }
  };

  const handleEdit = async (payload: AgentFormPayload) => {
    if (!teamId || !editingInstance) return;
    const request: UpdateAgentInstanceRequest = {
      display_name: payload.displayName,
      role: payload.role || undefined,
      description: payload.description || undefined,
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
      await refetchInstances();
    } catch (error: unknown) {
      showError({
        summary: t("rework.agentCard.updateError", { agent: agentsNicknameSingular.toLowerCase() }),
        detail: extractApiErrorDetail(error) ?? t("rework.agentCard.unexpectedError"),
      });
    }
  };

  const handleToggleEnabled = async (instance: ManagedAgentInstanceSummary) => {
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
    const template = availableTemplates.find((tpl) => tpl.template_id === source.template_id);
    // Reuse the same payload-building as the normal enroll form (#2096) —
    // correct capability filtering against the current template state —
    // rather than hand-rebuilding a parallel, easier-to-get-subtly-wrong
    // CreateAgentInstanceRequest straight from the source instance's stored
    // fields. Not reusing `handleEnroll` itself: it always closes/resets the
    // *enroll* modal's own state, which is wrong for the duplicate dialog.
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: source.template_id,
        displayName: newName,
        role: source.role,
        description: source.description ?? "",
        tuningValues: (source.tuning_field_values as Record<string, unknown>) ?? {},
        selectedCapabilityIds: source.selected_capability_ids ?? [],
        capabilityConfigValues: extractCapabilityConfigValues(source.capability_config),
        capabilityAssetFiles: {},
        capabilityBlockingErrors: {},
      },
      template,
    );
    const request: CreateAgentInstanceRequest = {
      template_id: payload.templateId,
      display_name: payload.displayName,
      role: payload.role || undefined,
      description: payload.description || undefined,
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
      await createManagedInstance({ teamId, createAgentInstanceRequest: request }).unwrap();
      showSuccess({ summary: t("rework.agentCard.duplicateSuccess", { agent: agentsNicknameSingular }) });
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
      message: t("rework.agentCard.deleteDialog.message", { name: instance.display_name }),
      confirmButtonLabel: t("rework.agentCard.deleteDialog.confirm"),
      cancelButtonLabel: t("rework.agentCard.deleteDialog.cancel"),
      // Same inverted emphasis as "Leave team" — Cancel stays the visually
      // dominant filled button, Delete drops to a low-emphasis text button.
      cancelVariant: "filled",
      cancelColor: "primary",
      confirmVariant: "text",
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

  return (
    <div className={styles.teamAgentContainer}>
      {hasAgents && !templatesUnavailable && (
        <div className={styles.title}>
          <span>{t("rework.teams.agents.title", { agentsNicknamePlural })}</span>
          {canManageAgents && (
            <Button
              color={"primary"}
              variant={"filled"}
              size={"medium"}
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setIsEnrollOpen(true)}
            >
              {t("rework.teams.agents.create", { agentsNicknameSingular })}
            </Button>
          )}
        </div>
      )}

      {isLoadingInstances ? (
        <div className={styles.loadingState}>
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
      ) : (
        <div className={styles.agentList}>
          {managedInstances
            // #1975 (RFC §3.9): a suspended agent is hidden from chat-only
            // members (they cannot fix it and must not see a broken agent);
            // editors/owners (`can_update_agents`) keep seeing it with a warning
            // and a locked enable toggle so they can open the edit form and fix.
            .filter((instance) => canManageAgents || !instance.suspension_reason)
            .map((instance) => {
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
                  onDuplicate={() => setDuplicatingInstance(instance)}
                  onDelete={() => handleDelete(instance)}
                />
              );
            })}
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
      />

      <DuplicateAgentDialog
        open={duplicatingInstance !== null}
        initialName={duplicatingInstance?.display_name ?? ""}
        isSubmitting={isCreatingInstance}
        onCancel={() => setDuplicatingInstance(null)}
        onConfirm={(newName) => {
          if (duplicatingInstance) void handleDuplicate(duplicatingInstance, newName);
        }}
      />
    </div>
  );
}
