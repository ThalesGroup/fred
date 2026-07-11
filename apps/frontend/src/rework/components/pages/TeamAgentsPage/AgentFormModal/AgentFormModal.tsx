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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type {
  AgentTemplateSummary,
  ManagedAgentFieldSpec,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { sanitizeMcpConfigValuesForTemplate } from "./chatOptionsConfig.ts";
import { AgentFormBody, type SectionKey } from "./AgentFormBody.tsx";
import styles from "./AgentFormModal.module.css";
import { TemplateBrowser } from "./TemplateBrowser/TemplateBrowser.tsx";

export type AgentFormPayload = {
  templateId: string;
  displayName: string;
  description: string;
  tuningFieldValues: Record<string, unknown>;
  selectedMcpServerIds: string[] | null;
  /** Per-server MCP config values: outer key = server id, inner key = config_fields[].key. */
  mcpConfigValues: Record<string, Record<string, unknown>>;
  /** Explicit list of active capability ids ([] = none active). */
  selectedCapabilityIds: string[];
  /** Per-capability config values: outer key = capability id, inner key = config_fields[].key. */
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  /**
   * True when the chosen template advertises at least one capability. When false
   * the caller omits capability fields from the request so a plain edit of a
   * capability-less agent never triggers the backend's live-pod capability
   * re-validation.
   */
  templateHasCapabilities: boolean;
};

type AgentFormModalProps = {
  isOpen: boolean;
  isSubmitting: boolean;
  mode: "create" | "edit";
  teamName?: string;
  teamId?: string;
  templates: AgentTemplateSummary[];
  editInstance?: ManagedAgentInstanceSummary;
  onClose: () => void;
  onSubmit: (payload: AgentFormPayload) => Promise<void>;
  onDelete?: () => void;
};

type FormState = {
  templateId: string;
  displayName: string;
  description: string;
  tuningValues: Record<string, unknown>;
  selectedMcpServerIds: string[] | null;
  mcpConfigValues: Record<string, Record<string, unknown>>;
  selectedCapabilityIds: string[];
  capabilityConfigValues: Record<string, Record<string, unknown>>;
};

function sectionOfField(field: ManagedAgentFieldSpec): SectionKey {
  const g = (field.ui?.group ?? "").toLowerCase().trim();
  if (g === "prompts") return "prompts";
  if (g === "chat") return "chat";
  return "settings";
}

/**
 * Builds the submit payload using the selected template contract so stale MCP
 * keys from previous UI versions cannot leak into create or edit requests.
 */
export function buildAgentFormSubmitPayload(
  form: FormState,
  selectedTemplate: AgentTemplateSummary | undefined,
): AgentFormPayload {
  const lockedIds = (selectedTemplate?.mcp_servers ?? []).filter((server) => server.locked).map((server) => server.id);
  const effectiveSelection =
    form.selectedMcpServerIds === null ? null : [...new Set([...form.selectedMcpServerIds, ...lockedIds])];

  // Only active capabilities are advertised by the template; drop selections and
  // config slices for ids the template no longer exposes, and for capabilities
  // that are not currently ticked, so deselected config never reaches the pod.
  const availableCapabilityIds = new Set((selectedTemplate?.available_capabilities ?? []).map((cap) => cap.id));
  const effectiveCapabilityIds = form.selectedCapabilityIds.filter((id) => availableCapabilityIds.has(id));
  const effectiveCapabilityConfig = Object.fromEntries(
    Object.entries(form.capabilityConfigValues).filter(([id]) => effectiveCapabilityIds.includes(id)),
  );

  return {
    templateId: form.templateId,
    displayName: form.displayName.trim(),
    description: form.description.trim(),
    tuningFieldValues: form.tuningValues,
    selectedMcpServerIds: effectiveSelection,
    mcpConfigValues: sanitizeMcpConfigValuesForTemplate(form.mcpConfigValues, selectedTemplate?.mcp_servers ?? []),
    selectedCapabilityIds: effectiveCapabilityIds,
    capabilityConfigValues: effectiveCapabilityConfig,
    templateHasCapabilities: availableCapabilityIds.size > 0,
  };
}

/**
 * Unwraps the persisted per-capability `{schema_version, config}` envelopes into
 * the flat `{ [capabilityId]: config }` shape the edit form renders and mutates.
 */
export function extractCapabilityConfigValues(
  storedConfig: ManagedAgentInstanceSummary["capability_config"],
): Record<string, Record<string, unknown>> {
  if (!storedConfig) return {};
  return Object.fromEntries(
    Object.entries(storedConfig).map(([id, envelope]) => [
      id,
      (envelope as { config?: Record<string, unknown> })?.config ?? {},
    ]),
  );
}

export default function AgentFormModal({
  isOpen,
  isSubmitting,
  mode,
  teamName,
  teamId,
  templates,
  editInstance,
  onClose,
  onSubmit,
  onDelete,
}: AgentFormModalProps) {
  const { t, i18n } = useTranslation();
  const { agentsNicknameSingular, agentIconName } = useFrontendProperties();

  // step 1 = choose template, step 2 = configure. Edit mode always starts at 2.
  const [step, setStep] = useState<1 | 2>(1);

  const [form, setForm] = useState<FormState>({
    templateId: "",
    displayName: "",
    description: "",
    tuningValues: {},
    selectedMcpServerIds: [],
    mcpConfigValues: {},
    selectedCapabilityIds: [],
    capabilityConfigValues: {},
  });
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [activeSection, setActiveSection] = useState<SectionKey>("settings");

  useEffect(() => {
    if (!isOpen) {
      setSubmitAttempted(false);
      setActiveSection("settings");
      return;
    }
    if (mode === "edit" && editInstance) {
      setForm({
        templateId: editInstance.template_id,
        displayName: editInstance.display_name,
        description: editInstance.description ?? "",
        tuningValues: (editInstance.tuning_field_values as Record<string, unknown>) ?? {},
        // Preserve tri-state: null = inherit default, [] = none, [...] = exact subset.
        selectedMcpServerIds: editInstance.selected_mcp_server_ids ?? null,
        mcpConfigValues: (editInstance.mcp_config_values as Record<string, Record<string, unknown>>) ?? {},
        selectedCapabilityIds: editInstance.selected_capability_ids ?? [],
        // capability_config stores the {schema_version, config} envelope per id;
        // the form edits the inner `config` object only.
        capabilityConfigValues: extractCapabilityConfigValues(editInstance.capability_config),
      });
      setStep(2);
    } else {
      setForm({
        templateId: "",
        displayName: "",
        description: "",
        tuningValues: {},
        selectedMcpServerIds: [],
        mcpConfigValues: {},
        selectedCapabilityIds: [],
        capabilityConfigValues: {},
      });
      setStep(1);
    }
  }, [isOpen, mode, editInstance]);

  const handleTemplateSelect = (id: string) => {
    const tpl = templates.find((t) => t.template_id === id);
    const lang = i18n.language.split("-")[0];
    const defaultTuningValues = Object.fromEntries(
      (tpl?.default_tuning_fields ?? [])
        .filter((f) => f.default_by_lang?.[lang] != null || (f.default !== null && f.default !== undefined))
        .map((f) => [f.key, f.default_by_lang?.[lang] ?? f.default]),
    );
    setForm({
      templateId: id,
      displayName: tpl?.display_name ?? "",
      description: tpl?.description_by_lang?.[lang] ?? tpl?.description ?? "",
      tuningValues: defaultTuningValues,
      selectedMcpServerIds: [],
      mcpConfigValues: {},
      selectedCapabilityIds: [],
      capabilityConfigValues: {},
    });
    setActiveSection("settings");
    setSubmitAttempted(false);
    setStep(2);
  };

  const handleTuningChange = (key: string, value: unknown) => {
    setForm((prev) => ({ ...prev, tuningValues: { ...prev.tuningValues, [key]: value } }));
  };

  const handleMcpConfigChange = (serverId: string, key: string, value: unknown) => {
    setForm((prev) => ({
      ...prev,
      mcpConfigValues: {
        ...prev.mcpConfigValues,
        [serverId]: { ...prev.mcpConfigValues[serverId], [key]: value },
      },
    }));
  };

  const handleCapabilityConfigChange = (capabilityId: string, key: string, value: unknown) => {
    setForm((prev) => ({
      ...prev,
      capabilityConfigValues: {
        ...prev.capabilityConfigValues,
        [capabilityId]: { ...prev.capabilityConfigValues[capabilityId], [key]: value },
      },
    }));
  };

  const selectedTemplate = templates.find((tpl) => tpl.template_id === form.templateId);
  const requiredFields = (selectedTemplate?.default_tuning_fields ?? []).filter((f) => f.required && !f.ui?.hide);
  const missingRequired = requiredFields.some((f) => !form.tuningValues[f.key]);
  const isFormValid = !!form.templateId && !!form.displayName.trim() && !missingRequired;
  const canSave = isFormValid && !isSubmitting;

  const errorSections = new Set<SectionKey>(
    submitAttempted ? requiredFields.filter((f) => !form.tuningValues[f.key]).map((f) => sectionOfField(f)) : [],
  );

  const handleSubmit = async () => {
    setSubmitAttempted(true);
    if (!canSave) {
      const firstErrorSection = (["prompts", "settings", "chat"] as const).find((s) => {
        return requiredFields.some((f) => !form.tuningValues[f.key] && sectionOfField(f) === s);
      });
      if (firstErrorSection) setActiveSection(firstErrorSection);
      return;
    }
    await onSubmit(buildAgentFormSubmitPayload(form, selectedTemplate));
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
              <div className={styles.modalSubtitle}>{teamName || t("rework.sidebar.team.userTeam")}</div>
            </div>
          </div>

          <div className={styles.modalActions}>
            {mode === "create" && step === 2 && (
              <div className={styles.modalActionsBack}>
                <Button
                  color="on-surface"
                  variant="text"
                  size="medium"
                  icon={{ category: "outlined", type: "arrow_back" }}
                  onClick={() => setStep(1)}
                >
                  {t("rework.back")}
                </Button>
              </div>
            )}
            <Button color="primary" variant="text" size="medium" onClick={onClose}>
              {t("rework.cancel")}
            </Button>
            {step === 2 && (
              <Button
                color={submitAttempted && !isFormValid ? "warning" : "primary"}
                variant="filled"
                size="medium"
                onClick={handleSubmit}
              >
                {mode === "edit" ? t("rework.save") : t("rework.create")}
              </Button>
            )}
          </div>
        </div>

        <div className={styles.modalContent}>
          {step === 1 ? (
            <TemplateBrowser templates={templates} selectedId={form.templateId} onSelect={handleTemplateSelect} />
          ) : (
            <AgentFormBody
              mode={mode}
              templates={templates}
              templateId={form.templateId}
              displayName={form.displayName}
              description={form.description}
              tuningFieldValues={form.tuningValues}
              selectedMcpServerIds={form.selectedMcpServerIds}
              mcpConfigValues={form.mcpConfigValues}
              selectedCapabilityIds={form.selectedCapabilityIds}
              capabilityConfigValues={form.capabilityConfigValues}
              isSubmitting={isSubmitting}
              submitAttempted={submitAttempted}
              activeSection={activeSection}
              onSectionChange={setActiveSection}
              errorSections={errorSections}
              editInstance={editInstance}
              teamId={teamId}
              onDisplayNameChange={(v) => setForm((prev) => ({ ...prev, displayName: v }))}
              onDescriptionChange={(v) => setForm((prev) => ({ ...prev, description: v }))}
              onTuningChange={handleTuningChange}
              onMcpSelectionChange={(ids) => setForm((prev) => ({ ...prev, selectedMcpServerIds: ids }))}
              onMcpConfigChange={handleMcpConfigChange}
              onCapabilitySelectionChange={(ids) => setForm((prev) => ({ ...prev, selectedCapabilityIds: ids }))}
              onCapabilityConfigChange={handleCapabilityConfigChange}
            />
          )}
        </div>

        {mode === "edit" && onDelete && (
          <div className={styles.modalFooter}>
            <Button color="error" variant="outlined" size="medium" onClick={onDelete}>
              {t("rework.delete")}
            </Button>
          </div>
        )}
      </div>
    </FullPageModal>
  );
}
