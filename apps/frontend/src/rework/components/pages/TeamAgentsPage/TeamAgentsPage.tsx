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
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useConfirmationDialog } from "../../../../components/ConfirmationDialogProvider";
import { useToast } from "../../../../components/ToastProvider";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { type AgentFormPayload, default as AgentFormModal } from "./AgentFormModal/AgentFormModal.tsx";
import TeamAgentEmptyState from "./TeamAgentEmptyState/TeamAgentEmptyState.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import {
  type CreateAgentInstanceRequest,
  type ManagedAgentInstanceSummary,
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useState } from "react";
import styles from "./TeamAgentsPage.module.css";

type AgentRequestTuningFieldValues = NonNullable<CreateAgentInstanceRequest["tuning_field_values"]>;
type AgentRequestMcpConfigValues = NonNullable<CreateAgentInstanceRequest["mcp_config_values"]>;

function extractApiErrorDetail(error: unknown): string {
  if (typeof error !== "object" || error === null) return String(error);
  const data = (error as Record<string, unknown>).data;
  if (typeof data === "object" && data !== null) {
    const detail = (data as Record<string, unknown>).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e) => (typeof e === "object" && e !== null ? String((e as Record<string, unknown>).msg ?? JSON.stringify(e)) : String(e)))
        .join("; ");
    }
  }
  const msg = (error as Record<string, unknown>).message;
  return typeof msg === "string" ? msg : "An unexpected error occurred.";
}

/**
 * Lists the managed agent instances for the current team and exposes
 * create / edit / delete operations for team admins.
 *
 * Enabled agents are wrapped in a <Link> so the whole card navigates to the
 * managed-chat route. Disabled agents render the card without navigation.
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

  const { data: fetchedTeam } = useGetTeamQuery({ teamId: teamId || "" }, { skip: !teamId || isPersonalTeam });
  const team = isPersonalTeam ? activeTeam : fetchedTeam;
  const canManageAgents = Array.isArray(team?.permissions) ? team.permissions.includes("can_update_agents") : false;

  const {
    data: managedInstances = [],
    isLoading: isLoadingInstances,
    refetch: refetchInstances,
  } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId: teamId || "" },
    { skip: !teamId },
  );

  const { data: availableTemplates = [], isLoading: isLoadingTemplates } =
    useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery(
      { teamId: teamId || "" },
      { skip: !teamId || !canManageAgents },
    );

  const [createManagedInstance, { isLoading: isCreatingInstance }] =
    usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation();
  const [patchManagedInstance, { isLoading: isUpdatingInstance }] =
    usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation();
  const [deleteManagedInstance] =
    useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation();

  const handleEnroll = async (payload: AgentFormPayload) => {
    if (!teamId) return;
    try {
      await createManagedInstance({
        teamId,
        createAgentInstanceRequest: {
          template_id: payload.templateId,
          display_name: payload.displayName,
          description: payload.description || undefined,
          tuning_field_values:
            Object.keys(payload.tuningFieldValues).length > 0
              ? (payload.tuningFieldValues as AgentRequestTuningFieldValues)
              : undefined,
          mcp_server_ids: payload.selectedMcpServerIds ?? undefined,
          mcp_config_values:
            Object.keys(payload.mcpConfigValues).length > 0
              ? (payload.mcpConfigValues as AgentRequestMcpConfigValues)
              : undefined,
        },
      }).unwrap();
      showSuccess({ summary: `${agentsNicknameSingular} created` });
      setIsEnrollOpen(false);
      await refetchInstances();
    } catch (error: unknown) {
      showError({
        summary: `Failed to create ${agentsNicknameSingular.toLowerCase()}`,
        detail: extractApiErrorDetail(error),
      });
    }
  };

  const handleEdit = async (payload: AgentFormPayload) => {
    if (!teamId || !editingInstance) return;
    // When selectedMcpServerIds is an explicit list, drop config for servers
    // that are no longer selected so the backend doesn't reject the request.
    const activeMcpConfig =
      payload.selectedMcpServerIds === null
        ? payload.mcpConfigValues
        : Object.fromEntries(
            Object.entries(payload.mcpConfigValues).filter(([id]) =>
              payload.selectedMcpServerIds!.includes(id),
            ),
          );
    try {
      await patchManagedInstance({
        teamId,
        agentInstanceId: editingInstance.agent_instance_id,
        updateAgentInstanceRequest: {
          display_name: payload.displayName,
          description: payload.description || undefined,
          tuning_field_values:
            Object.keys(payload.tuningFieldValues).length > 0
              ? (payload.tuningFieldValues as AgentRequestTuningFieldValues)
              : undefined,
          mcp_server_ids: payload.selectedMcpServerIds ?? undefined,
          mcp_config_values:
            Object.keys(activeMcpConfig).length > 0
              ? (activeMcpConfig as AgentRequestMcpConfigValues)
              : undefined,
        },
      }).unwrap();
      showSuccess({ summary: `${agentsNicknameSingular} updated` });
      setEditingInstance(null);
      await refetchInstances();
    } catch (error: unknown) {
      showError({
        summary: `Failed to update ${agentsNicknameSingular.toLowerCase()}`,
        detail: extractApiErrorDetail(error),
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
      showSuccess({ summary: `${agentsNicknameSingular} ${newStatus}` });
      await refetchInstances();
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: `Failed to update ${agentsNicknameSingular.toLowerCase()}`,
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  const handleDelete = (instance: ManagedAgentInstanceSummary) => {
    if (!teamId) return;
    showConfirmationDialog({
      criticalAction: true,
      title: `Delete ${agentsNicknameSingular.toLowerCase()}?`,
      message: `Remove "${instance.display_name}" from this team?`,
      onConfirm: async () => {
        try {
          await deleteManagedInstance({
            teamId,
            agentInstanceId: instance.agent_instance_id,
          }).unwrap();
          showSuccess({ summary: `${agentsNicknameSingular} deleted` });
          setEditingInstance(null);
          await refetchInstances();
        } catch (error: unknown) {
          const err = error as { data?: { detail?: string }; message?: string };
          showError({
            summary: `Failed to delete ${agentsNicknameSingular.toLowerCase()}`,
            detail: err?.data?.detail || err?.message || String(error),
          });
        }
      },
    });
  };

  if (!teamId) {
    return <div className={styles.pageError}>Missing team id in route.</div>;
  }

  const templatesUnavailable = canManageAgents && !isLoadingTemplates && availableTemplates.length === 0;
  const showEmptyState = !isLoadingInstances && managedInstances.length === 0;

  return (
    <div className={styles.teamAgentContainer}>
      <div className={styles.title}>
        <span>{t("rework.teams.agents.title", { agentsNicknamePlural })}</span>
        {canManageAgents && (
          <Button
            color={"primary"}
            variant={"filled"}
            size={"medium"}
            icon={{ category: "outlined", type: "add" }}
            onClick={() => setIsEnrollOpen(true)}
            disabled={templatesUnavailable}
          >
            {t("rework.teams.agents.create", { agentsNicknameSingular })}
          </Button>
        )}
      </div>

      {templatesUnavailable && (
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.serviceNotice.agentTemplates.title")}
          description={t("rework.serviceNotice.agentTemplates.description")}
        />
      )}

      {isLoadingInstances ? (
        <div className={styles.loadingState}>
          {t("rework.teams.agents.loading", { agentsNicknamePlural: agentsNicknamePlural.toLowerCase() })}
        </div>
      ) : showEmptyState ? (
        <TeamAgentEmptyState
          canManageAgents={canManageAgents}
          templatesUnavailable={templatesUnavailable}
          onCreateAgent={() => setIsEnrollOpen(true)}
        />
      ) : (
        <div className={styles.agentList}>
          {managedInstances.map((instance) => {
            const template = availableTemplates.find((tpl) => tpl.template_id === instance.template_id);
            const card = (
              <AgentCard
                instance={instance}
                templateDisplayName={template?.display_name || instance.template_id}
                templateCategory={template?.category}
                canManageAgents={canManageAgents}
                onEdit={() => setEditingInstance(instance)}
                onToggleEnabled={() => handleToggleEnabled(instance)}
              />
            );

            return instance.status === "enabled" ? (
              <Link
                key={instance.agent_instance_id}
                to={`/team/${teamId}/managed-chat/${instance.agent_instance_id}`}
                className={styles.chatLink}
              >
                {card}
              </Link>
            ) : (
              <div key={instance.agent_instance_id} className={styles.disabledCard}>
                {card}
              </div>
            );
          })}
        </div>
      )}

      <AgentFormModal
        isOpen={isEnrollOpen || editingInstance !== null}
        isSubmitting={isCreatingInstance || isUpdatingInstance}
        mode={editingInstance ? "edit" : "create"}
        editInstance={editingInstance ?? undefined}
        teamName={team?.name}
        teamId={teamId}
        templates={availableTemplates}
        onClose={() => {
          setIsEnrollOpen(false);
          setEditingInstance(null);
        }}
        onSubmit={editingInstance ? handleEdit : handleEnroll}
        onDelete={editingInstance ? () => handleDelete(editingInstance) : undefined}
      />
    </div>
  );
}
