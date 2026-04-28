import Button from "@shared/atoms/Button/Button.tsx";
import AgentCard from "@shared/organisms/AgentCard/AgentCard.tsx";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useConfirmationDialog } from "../../../../components/ConfirmationDialogProvider";
import { useToast } from "../../../../components/ToastProvider";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  type AgentFormPayload,
  default as AgentFormModal,
} from "./AgentFormModal/AgentFormModal.tsx";
import TeamAgentEmptyState from "./TeamAgentEmptyState/TeamAgentEmptyState.tsx";
import {
  type ManagedAgentInstanceSummary,
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useState } from "react";
import styles from "./TeamAgentsPage.module.css";

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

  const { data: fetchedTeam } = useGetTeamQuery(
    { teamId: teamId || "" },
    { skip: !teamId || isPersonalTeam },
  );
  const team = isPersonalTeam ? activeTeam : fetchedTeam;
  const canManageAgents = Array.isArray(team?.permissions)
    ? team.permissions.includes("can_update_agents")
    : false;

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
              ? payload.tuningFieldValues
              : undefined,
        },
      }).unwrap();
      showSuccess({ summary: `${agentsNicknameSingular} created` });
      setIsEnrollOpen(false);
      await refetchInstances();
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: `Failed to create ${agentsNicknameSingular.toLowerCase()}`,
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  const handleEdit = async (payload: AgentFormPayload) => {
    if (!teamId || !editingInstance) return;
    try {
      await patchManagedInstance({
        teamId,
        agentInstanceId: editingInstance.agent_instance_id,
        updateAgentInstanceRequest: {
          display_name: payload.displayName,
          description: payload.description || undefined,
          tuning_field_values:
            Object.keys(payload.tuningFieldValues).length > 0
              ? payload.tuningFieldValues
              : undefined,
        },
      }).unwrap();
      showSuccess({ summary: `${agentsNicknameSingular} updated` });
      setEditingInstance(null);
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
        <div className={styles.bannerNotice}>
          No agent templates are currently available for this team. Start a runtime pod to enroll
          managed agents.
        </div>
      )}

      {isLoadingInstances ? (
        <div className={styles.loadingState}>
          Loading {agentsNicknamePlural.toLowerCase()}…
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
            const template = availableTemplates.find(
              (tpl) => tpl.template_id === instance.template_id,
            );
            const card = (
              <AgentCard
                instance={instance}
                templateDisplayName={template?.display_name || instance.template_id}
                templateCategory={template?.category}
                canManageAgents={canManageAgents}
                onEdit={() => setEditingInstance(instance)}
                onDelete={() => handleDelete(instance)}
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
        templates={availableTemplates}
        onClose={() => {
          setIsEnrollOpen(false);
          setEditingInstance(null);
        }}
        onSubmit={editingInstance ? handleEdit : handleEnroll}
      />
    </div>
  );
}
