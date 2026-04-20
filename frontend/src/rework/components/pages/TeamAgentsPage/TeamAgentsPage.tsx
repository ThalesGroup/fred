import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useConfirmationDialog } from "../../../../components/ConfirmationDialogProvider";
import { useToast } from "../../../../components/ToastProvider";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  type AgentTemplateSummary,
  type ManagedAgentInstanceSummary,
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamAgentsPage.module.css";

type EnrollManagedAgentModalProps = {
  isOpen: boolean;
  isSubmitting: boolean;
  teamName?: string;
  templates: AgentTemplateSummary[];
  onClose: () => void;
  onSubmit: (payload: { templateId: string; displayName: string; description: string }) => Promise<void>;
};

/**
 * Collect the minimal team-facing information required to enroll one managed
 * agent instance from a discovered template.
 *
 * Why this component exists:
 * - the managed-agent migration needs a small product-facing enrollment flow
 *   without reusing the legacy raw-agent authoring modal
 *
 * How to use it:
 * - mount it in `TeamAgentsPage` and pass the currently available templates plus
 *   an `onSubmit` handler that calls the control-plane enrollment endpoint
 *
 * Example:
 * - `<EnrollManagedAgentModal isOpen={open} templates={templates} onClose={...} onSubmit={...} />`
 */
function EnrollManagedAgentModal({
  isOpen,
  isSubmitting,
  teamName,
  templates,
  onClose,
  onSubmit,
}: EnrollManagedAgentModalProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular, agentIconName } = useFrontendProperties();
  const firstTemplateId = templates[0]?.template_id ?? "";
  const [templateId, setTemplateId] = useState(firstTemplateId);
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    const nextTemplateId = templates[0]?.template_id ?? "";
    setTemplateId(nextTemplateId);
    setDisplayName(templates[0]?.display_name ?? "");
    setDescription(templates[0]?.description ?? "");
  }, [isOpen, templates]);

  const selectedTemplate = templates.find((template) => template.template_id === templateId);

  /**
   * Keep enrollment defaults aligned with the selected template.
   *
   * Why this helper exists:
   * - enrolling managed agents should start from template metadata instead of
   *   forcing developers to re-enter display defaults by hand
   *
   * How to use it:
   * - pass the newly selected template id from the template picker
   */
  const handleTemplateChange = (nextTemplateId: string) => {
    const nextTemplate = templates.find((template) => template.template_id === nextTemplateId);
    setTemplateId(nextTemplateId);
    setDisplayName(nextTemplate?.display_name ?? "");
    setDescription(nextTemplate?.description ?? "");
  };

  /**
   * Submit one managed-agent enrollment request with the current form values.
   *
   * Why this helper exists:
   * - the modal should guard against empty selections before delegating to the
   *   control-plane mutation supplied by the page
   *
   * How to use it:
   * - call it from the modal primary action button
   */
  const handleSubmit = async () => {
    if (!templateId || !displayName.trim()) return;
    await onSubmit({
      templateId,
      displayName: displayName.trim(),
      description: description.trim(),
    });
  };

  return (
    <FullPageModal isOpen={isOpen} onClose={onClose} id={"enroll-managed-agent-modal"}>
      <div className={styles.modalCard}>
        <div className={styles.modalHeader}>
          <div className={styles.modalPresentation}>
            <span className={styles.modalIcon}>
              <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
            </span>
            <div className={styles.modalTitleBlock}>
              <div className={styles.modalTitle}>{t("rework.teams.formAgent.titleCreate", { agentsNicknameSingular })}</div>
              <div className={styles.modalSubtitle}>{teamName || t("rework.sidebar.team.userTeam")}</div>
            </div>
          </div>
          <div className={styles.modalActions}>
            <Button color={"primary"} variant={"text"} size={"medium"} onClick={onClose}>
              {t("rework.cancel")}
            </Button>
            <Button
              color={"primary"}
              variant={"filled"}
              size={"medium"}
              onClick={handleSubmit}
              disabled={!templateId || !displayName.trim() || isSubmitting}
            >
              {t("rework.create")}
            </Button>
          </div>
        </div>
        <div className={styles.modalContent}>
          <label className={styles.fieldLabel} htmlFor="managed-agent-template">
            Template
          </label>
          <select
            id="managed-agent-template"
            className={styles.templateSelect}
            value={templateId}
            onChange={(event) => handleTemplateChange(event.target.value)}
            disabled={isSubmitting || templates.length === 0}
          >
            {templates.map((template) => (
              <option key={template.template_id} value={template.template_id}>
                {template.display_name}
              </option>
            ))}
          </select>
          {selectedTemplate?.description && <p className={styles.templateHint}>{selectedTemplate.description}</p>}
          <TextInput
            label="Display name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            maxLength={255}
            required
            disabled={isSubmitting}
          />
          <TextArea
            label="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={4}
            maxLength={500}
            disabled={isSubmitting}
          />
        </div>
      </div>
    </FullPageModal>
  );
}

/**
 * Render the managed team-agent page backed by control-plane templates and
 * managed instances.
 *
 * Why this component exists:
 * - the migrated frontend should expose team-selectable managed agent instances
 *   instead of the legacy raw-agent list from `agentic-backend`
 *
 * How to use it:
 * - mount it on `/team/:teamId/agents`
 * - the page lists managed instances, supports template enrollment, and routes
 *   enabled instances to the managed chat page
 *
 * Example:
 * - `<TeamAgentsPage />`
 */
export default function TeamAgentsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { activeTeam } = useFrontendBootstrap();
  const { agentsNicknamePlural, agentsNicknameSingular, agentIconName } = useFrontendProperties();
  const personalTeamId = activeTeam?.id ?? "personal";
  const isPersonalTeam = teamId === personalTeamId;
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);

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
  const {
    data: availableTemplates = [],
    isLoading: isLoadingTemplates,
  } = useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery(
    { teamId: teamId || "" },
    { skip: !teamId || !canManageAgents },
  );

  const [createManagedInstance, { isLoading: isCreatingInstance }] =
    usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation();
  const [deleteManagedInstance] =
    useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation();

  /**
   * Enroll one managed agent instance for the current team.
   *
   * Why this helper exists:
   * - the managed-agent page should create product-owned instances directly in
   *   control-plane instead of falling back to legacy raw-agent authoring
   *
   * How to use it:
   * - pass it to `EnrollManagedAgentModal` as the submit handler
   */
  const handleEnrollManagedAgent = async (payload: {
    templateId: string;
    displayName: string;
    description: string;
  }) => {
    if (!teamId) return;
    try {
      await createManagedInstance({
        teamId,
        createAgentInstanceRequest: {
          template_id: payload.templateId,
          display_name: payload.displayName,
          description: payload.description || undefined,
        },
      }).unwrap();
      showSuccess({ summary: `${agentsNicknameSingular} created` });
      setIsEnrollOpen(false);
      await refetchInstances();
    } catch (error: any) {
      showError({
        summary: `Failed to create ${agentsNicknameSingular.toLowerCase()}`,
        detail: error?.data?.detail || error?.message || String(error),
      });
    }
  };

  /**
   * Delete one managed agent instance after an explicit confirmation step.
   *
   * Why this helper exists:
   * - managed-agent removal is a product action that should stay visible and
   *   deliberate for the owning team
   *
   * How to use it:
   * - call it from the delete button rendered on one agent card
   */
  const handleDeleteManagedAgent = (instance: ManagedAgentInstanceSummary) => {
    if (!teamId) return;
    showConfirmationDialog({
      criticalAction: true,
      title: `Delete ${agentsNicknameSingular.toLowerCase()}?`,
      message: `Remove “${instance.display_name}” from this team?`,
      onConfirm: async () => {
        try {
          await deleteManagedInstance({
            teamId,
            agentInstanceId: instance.agent_instance_id,
          }).unwrap();
          showSuccess({ summary: `${agentsNicknameSingular} deleted` });
          await refetchInstances();
        } catch (error: any) {
          showError({
            summary: `Failed to delete ${agentsNicknameSingular.toLowerCase()}`,
            detail: error?.data?.detail || error?.message || String(error),
          });
        }
      },
    });
  };

  if (!teamId) {
    return <div className={styles.pageError}>Missing team id in route.</div>;
  }

  const showEmptyState = !isLoadingInstances && managedInstances.length === 0;
  const templatesUnavailable = canManageAgents && !isLoadingTemplates && availableTemplates.length === 0;

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
          No agent templates are currently available for this team. Start a runtime pod to enroll managed agents.
        </div>
      )}

      {isLoadingInstances ? (
        <div className={styles.emptyState}>Loading {agentsNicknamePlural.toLowerCase()}…</div>
      ) : showEmptyState ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyStatePresentation}>
            <span className={styles.emptyStateIcon}>
              <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
            </span>
            <span>{t("rework.teams.agents.noAgent", { agentsNicknameSingular })}</span>
          </div>
          {canManageAgents && (
            <Button
              color={"primary"}
              variant={"filled"}
              size={"medium"}
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setIsEnrollOpen(true)}
              disabled={templatesUnavailable}
            >
              {t("rework.teams.agents.firstCreate", { agentsNicknameSingular })}
            </Button>
          )}
        </div>
      ) : (
        <div className={styles.agentList}>
          {managedInstances.map((instance) => {
            const template = availableTemplates.find((candidate) => candidate.template_id === instance.template_id);
            const isEnabled = instance.status === "enabled";

            return (
              <div key={instance.agent_instance_id} className={styles.agentCard} data-enabled={isEnabled}>
                <div className={styles.agentIdentity}>
                  <div className={styles.agentPresentation}>
                    <span className={styles.agentIcon}>
                      <Icon category={"outlined"} type={agentIconName as IconType} />
                    </span>
                    <div className={styles.agentHeading}>
                      <div className={styles.agentName}>{instance.display_name}</div>
                      <div className={styles.agentMeta}>
                        <span className={styles.agentStatus} data-status={instance.status}>
                          {instance.status}
                        </span>
                        {template?.category && <span>{template.category}</span>}
                      </div>
                    </div>
                  </div>
                  <div className={styles.agentDescription}>{instance.description || template?.description || "No description yet."}</div>
                </div>
                <div className={styles.agentFooter}>
                  <div className={styles.agentTemplate}>{template?.display_name || instance.template_id}</div>
                  <div className={styles.agentActions}>
                    {canManageAgents && (
                      <Button
                        color={"error"}
                        variant={"text"}
                        size={"medium"}
                        onClick={() => handleDeleteManagedAgent(instance)}
                      >
                        {t("common.delete")}
                      </Button>
                    )}
                    {isEnabled ? (
                      <Link to={`/team/${teamId}/managed-chat/${instance.agent_instance_id}`} className={styles.chatLink}>
                        <Button color={"primary"} variant={"filled"} size={"medium"}>
                          {t("rework.agentCard.startChat")}
                        </Button>
                      </Link>
                    ) : (
                      <Button color={"on-surface"} variant={"text"} size={"medium"} disabled>
                        {t("rework.agentCard.startChat")}
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <EnrollManagedAgentModal
        isOpen={isEnrollOpen}
        isSubmitting={isCreatingInstance}
        teamName={team?.name}
        templates={availableTemplates}
        onClose={() => setIsEnrollOpen(false)}
        onSubmit={handleEnrollManagedAgent}
      />
    </div>
  );
}
