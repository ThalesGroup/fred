import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
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
  type ManagedAgentFieldSpec,
  type ManagedAgentInstanceSummary,
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamAgentsPage.module.css";

type AgentFormPayload = {
  templateId: string;
  displayName: string;
  description: string;
  tuningFieldValues: Record<string, unknown>;
};

type AgentFormModalProps = {
  isOpen: boolean;
  isSubmitting: boolean;
  mode: "create" | "edit";
  teamName?: string;
  templates: AgentTemplateSummary[];
  editInstance?: ManagedAgentInstanceSummary;
  onClose: () => void;
  onSubmit: (payload: AgentFormPayload) => Promise<void>;
};

function renderTuningField(
  field: ManagedAgentFieldSpec,
  value: unknown,
  onChange: (key: string, value: unknown) => void,
  disabled: boolean,
): React.ReactNode {
  if (field.ui?.hide) return null;
  const fieldValue = value ?? field.default ?? "";

  if (field.enum && field.enum.length > 0) {
    return (
      <div key={field.key} className={styles.tuningField}>
        <label className={styles.fieldLabel} htmlFor={`tuning-${field.key}`}>
          {field.title}
          {field.required && " *"}
        </label>
        <select
          id={`tuning-${field.key}`}
          className={styles.templateSelect}
          value={String(fieldValue)}
          onChange={(e) => onChange(field.key, e.target.value)}
          disabled={disabled}
        >
          {field.enum.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        {field.description && <p className={styles.templateHint}>{field.description}</p>}
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <div key={field.key} className={styles.tuningField}>
        <label className={`${styles.fieldLabel} ${styles.tuningBooleanLabel}`}>
          <Switch
            checked={Boolean(fieldValue)}
            onChange={(e) => onChange(field.key, e.target.checked)}
            disabled={disabled}
          />
          {field.title}
        </label>
        {field.description && <p className={styles.templateHint}>{field.description}</p>}
      </div>
    );
  }

  if (field.ui?.multiline || field.ui?.textarea) {
    return (
      <TextArea
        key={field.key}
        label={`${field.title}${field.required ? " *" : ""}`}
        value={String(fieldValue)}
        onChange={(e) => onChange(field.key, e.target.value)}
        rows={field.ui.max_lines ?? 4}
        disabled={disabled}
      />
    );
  }

  return (
    <TextInput
      key={field.key}
      label={`${field.title}${field.required ? " *" : ""}`}
      value={String(fieldValue)}
      type={field.type === "number" ? "number" : "text"}
      onChange={(e) => onChange(field.key, field.type === "number" ? Number(e.target.value) : e.target.value)}
      disabled={disabled}
      required={field.required}
    />
  );
}

/**
 * Unified create/edit modal for managed agent instances.
 *
 * Why this component exists:
 * - enrollment (create) and settings (edit) share the same form surface: display
 *   name, description, and dynamic tuning fields declared by the template
 * - edit mode pre-fills from the existing instance and dispatches PATCH instead of POST
 *
 * How to use it:
 * - mount in `TeamAgentsPage`; pass `mode="create"` for enrollment or `mode="edit"`
 *   with `editInstance` for editing
 *
 * Example:
 * - `<AgentFormModal mode="edit" editInstance={instance} ... />`
 */
function AgentFormModal({
  isOpen,
  isSubmitting,
  mode,
  teamName,
  templates,
  editInstance,
  onClose,
  onSubmit,
}: AgentFormModalProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular, agentIconName } = useFrontendProperties();

  const [templateId, setTemplateId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [tuningFieldValues, setTuningFieldValues] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (!isOpen) return;
    if (mode === "edit" && editInstance) {
      setTemplateId(editInstance.template_id);
      setDisplayName(editInstance.display_name);
      setDescription(editInstance.description ?? "");
      setTuningFieldValues((editInstance.tuning_field_values as Record<string, unknown>) ?? {});
    } else {
      const firstTemplateId = templates[0]?.template_id ?? "";
      setTemplateId(firstTemplateId);
      setDisplayName(templates[0]?.display_name ?? "");
      setDescription(templates[0]?.description ?? "");
      setTuningFieldValues({});
    }
  }, [isOpen, mode, editInstance, templates]);

  const selectedTemplate = templates.find((t) => t.template_id === templateId);
  const tuningFields = (selectedTemplate?.default_tuning_fields ?? []).filter((f) => !f.ui?.hide);

  const handleTemplateChange = (nextId: string) => {
    const next = templates.find((t) => t.template_id === nextId);
    setTemplateId(nextId);
    setDisplayName(next?.display_name ?? "");
    setDescription(next?.description ?? "");
    setTuningFieldValues({});
  };

  const handleTuningChange = (key: string, value: unknown) => {
    setTuningFieldValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async () => {
    if (!templateId || !displayName.trim()) return;
    await onSubmit({
      templateId,
      displayName: displayName.trim(),
      description: description.trim(),
      tuningFieldValues,
    });
  };

  const title =
    mode === "edit"
      ? t("rework.teams.formAgent.titleEdit", { agent: editInstance?.display_name ?? "" })
      : t("rework.teams.formAgent.titleCreate", { agentsNicknameSingular });

  return (
    <FullPageModal isOpen={isOpen} onClose={onClose} id={"agent-form-modal"}>
      <div className={styles.modalCard}>
        <div className={styles.modalHeader}>
          <div className={styles.modalPresentation}>
            <span className={styles.modalIcon}>
              <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
            </span>
            <div className={styles.modalTitleBlock}>
              <div className={styles.modalTitle}>{title}</div>
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
              {mode === "edit" ? t("rework.save") : t("rework.create")}
            </Button>
          </div>
        </div>
        <div className={styles.modalContent}>
          {mode === "create" ? (
            <>
              <label className={styles.fieldLabel} htmlFor="managed-agent-template">
                Template
              </label>
              <select
                id="managed-agent-template"
                className={styles.templateSelect}
                value={templateId}
                onChange={(e) => handleTemplateChange(e.target.value)}
                disabled={isSubmitting || templates.length === 0}
              >
                {templates.map((template) => (
                  <option key={template.template_id} value={template.template_id}>
                    {template.display_name}
                  </option>
                ))}
              </select>
              {selectedTemplate?.description && <p className={styles.templateHint}>{selectedTemplate.description}</p>}
            </>
          ) : (
            <p className={styles.templateReadonly}>{selectedTemplate?.display_name ?? templateId}</p>
          )}

          <TextInput
            label={t("rework.teams.formAgent.fields.name.label")}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={255}
            required
            disabled={isSubmitting}
          />
          <TextArea
            label={t("rework.teams.formAgent.fields.description.label")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            maxLength={500}
            disabled={isSubmitting}
          />

          {tuningFields.length > 0 && (
            <div className={styles.tuningSection}>
              <span className={styles.tuningSectionHeader}>{t("rework.teams.formAgent.tunableFields")}</span>
              {tuningFields.map((field) =>
                renderTuningField(field, tuningFieldValues[field.key], handleTuningChange, isSubmitting),
              )}
            </div>
          )}
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

  /**
   * Enroll one managed agent instance for the current team.
   */
  const handleEnrollManagedAgent = async (payload: AgentFormPayload) => {
    if (!teamId) return;
    try {
      await createManagedInstance({
        teamId,
        createAgentInstanceRequest: {
          template_id: payload.templateId,
          display_name: payload.displayName,
          description: payload.description || undefined,
          tuning_field_values:
            Object.keys(payload.tuningFieldValues).length > 0 ? payload.tuningFieldValues : undefined,
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

  /**
   * Update display metadata and/or tuning field values for one existing instance.
   */
  const handleEditManagedAgent = async (payload: AgentFormPayload) => {
    if (!teamId || !editingInstance) return;
    try {
      await patchManagedInstance({
        teamId,
        agentInstanceId: editingInstance.agent_instance_id,
        updateAgentInstanceRequest: {
          display_name: payload.displayName,
          description: payload.description || undefined,
          tuning_field_values:
            Object.keys(payload.tuningFieldValues).length > 0 ? payload.tuningFieldValues : undefined,
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

  /**
   * Delete one managed agent instance after an explicit confirmation step.
   */
  const handleDeleteManagedAgent = (instance: ManagedAgentInstanceSummary) => {
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

            const cardBody = (
              <>
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
                  <div className={styles.agentDescription}>
                    {instance.description || template?.description || "No description yet."}
                  </div>
                </div>
                <div className={styles.agentFooter}>
                  <div className={styles.agentTemplate}>{template?.display_name || instance.template_id}</div>
                  <div className={styles.agentActions}>
                    {canManageAgents && (
                      <Button
                        color={"error"}
                        variant={"text"}
                        size={"medium"}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          handleDeleteManagedAgent(instance);
                        }}
                      >
                        {t("common.delete")}
                      </Button>
                    )}
                    {canManageAgents && (
                      <Button
                        color={"on-surface"}
                        variant={"text"}
                        size={"medium"}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setEditingInstance(instance);
                        }}
                      >
                        {t("rework.agentCard.settings", "Settings")}
                      </Button>
                    )}
                  </div>
                </div>
              </>
            );

            return isEnabled ? (
              <Link
                key={instance.agent_instance_id}
                to={`/team/${teamId}/managed-chat/${instance.agent_instance_id}`}
                className={styles.chatLink}
              >
                <div className={styles.agentCard} data-enabled={true}>
                  {cardBody}
                </div>
              </Link>
            ) : (
              <div key={instance.agent_instance_id} className={styles.agentCard} data-enabled={false}>
                {cardBody}
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
        onSubmit={editingInstance ? handleEditManagedAgent : handleEnrollManagedAgent}
      />
    </div>
  );
}
