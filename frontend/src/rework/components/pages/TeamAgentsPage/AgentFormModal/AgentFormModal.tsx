import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { AgentFormBody } from "./AgentFormBody.tsx";
import styles from "./AgentFormModal.module.css";

export type AgentFormPayload = {
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

type FormState = {
  templateId: string;
  displayName: string;
  description: string;
  tuningValues: Record<string, unknown>;
};

export default function AgentFormModal({
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
  const [form, setForm] = useState<FormState>({
    templateId: "",
    displayName: "",
    description: "",
    tuningValues: {},
  });
  const [submitAttempted, setSubmitAttempted] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setSubmitAttempted(false);
      return;
    }
    if (mode === "edit" && editInstance) {
      setForm({
        templateId: editInstance.template_id,
        displayName: editInstance.display_name,
        description: editInstance.description ?? "",
        tuningValues: (editInstance.tuning_field_values as Record<string, unknown>) ?? {},
      });
    } else {
      const first = templates[0];
      setForm({
        templateId: first?.template_id ?? "",
        displayName: first?.display_name ?? "",
        description: first?.description ?? "",
        tuningValues: {},
      });
    }
  }, [isOpen, mode, editInstance, templates]);

  const handleTemplateSelect = (id: string) => {
    const tpl = templates.find((t) => t.template_id === id);
    setForm({
      templateId: id,
      displayName: tpl?.display_name ?? "",
      description: tpl?.description ?? "",
      tuningValues: {},
    });
  };

  const handleTuningChange = (key: string, value: unknown) => {
    setForm((prev) => ({ ...prev, tuningValues: { ...prev.tuningValues, [key]: value } }));
  };

  const selectedTemplate = templates.find((tpl) => tpl.template_id === form.templateId);
  const requiredTuningKeys = (selectedTemplate?.default_tuning_fields ?? [])
    .filter((f) => f.required && !f.ui?.hide)
    .map((f) => f.key);
  const missingRequired = requiredTuningKeys.some((k) => !form.tuningValues[k]);
  const canSave = !!form.templateId && !!form.displayName.trim() && !missingRequired && !isSubmitting;

  const handleSubmit = async () => {
    setSubmitAttempted(true);
    if (!canSave) return;
    await onSubmit({
      templateId: form.templateId,
      displayName: form.displayName.trim(),
      description: form.description.trim(),
      tuningFieldValues: form.tuningValues,
    });
  };

  const title =
    mode === "edit"
      ? t("rework.teams.formAgent.titleEdit", { agent: editInstance?.display_name ?? "" })
      : t("rework.teams.formAgent.titleCreate", { agentsNicknameSingular });

  return (
    <FullPageModal isOpen={isOpen} onClose={onClose} id="agent-form-modal">
      <div className={styles.modalCard}>
        <div className={styles.modalHeader}>
          <div className={styles.modalPresentation}>
            <span className={styles.modalIcon}>
              <Icon category="outlined" type={agentIconName as IconType} filled={true} />
            </span>
            <div className={styles.modalTitleBlock}>
              <div className={styles.modalTitle}>{title}</div>
              <div className={styles.modalSubtitle}>
                {teamName || t("rework.sidebar.team.userTeam")}
              </div>
            </div>
          </div>
          <div className={styles.modalActions}>
            <Button color="primary" variant="text" size="medium" onClick={onClose}>
              {t("rework.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              onClick={handleSubmit}
              disabled={!form.templateId || !form.displayName.trim() || isSubmitting}
            >
              {mode === "edit" ? t("rework.save") : t("rework.create")}
            </Button>
          </div>
        </div>

        <div className={styles.modalContent}>
          <AgentFormBody
            mode={mode}
            templates={templates}
            templateId={form.templateId}
            displayName={form.displayName}
            description={form.description}
            tuningFieldValues={form.tuningValues}
            isSubmitting={isSubmitting}
            submitAttempted={submitAttempted}
            editInstance={editInstance}
            onTemplateSelect={handleTemplateSelect}
            onDisplayNameChange={(v) => setForm((prev) => ({ ...prev, displayName: v }))}
            onDescriptionChange={(v) => setForm((prev) => ({ ...prev, description: v }))}
            onTuningChange={handleTuningChange}
          />
        </div>
      </div>
    </FullPageModal>
  );
}
