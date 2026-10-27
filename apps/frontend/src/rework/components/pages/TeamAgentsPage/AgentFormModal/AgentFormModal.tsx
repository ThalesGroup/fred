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
import SettingsModal from "@shared/organisms/SettingsModal/SettingsModal.tsx";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import type { FieldSpec as ManagedAgentFieldSpec } from "../../../../../slices/runtime/runtimeOpenApi";
import { AgentFormBody, type SectionKey } from "./AgentFormBody.tsx";

import styles from "./AgentFormModal.module.css";
import { TemplateBrowser } from "./TemplateBrowser/TemplateBrowser.tsx";
import { applyDocumentAccessConfigChange } from "./toolPackLogic.ts";
import { CAP_DOCUMENT_ACCESS } from "./toolPacks.ts";
import { reservedTagInPromptField } from "@rework/utils/promptValidation";
import { hasTuningChanges } from "../weaverAgents";
import { isAgentNameTaken } from "../agentNames.ts";

export type AgentFormPayload = {
  templateId: string;
  displayName: string;
  role: string;
  description: string;
  usageStatement: string;
  /** Chat profile new conversations start on; null follows the team default. */
  recommendedChatProfileId: string | null;
  tuningFieldValues: Record<string, unknown>;
  /** Explicit list of active capability ids ([] = none active). */
  selectedCapabilityIds: string[];
  /** Per-capability config values: outer key = capability id, inner key = config_fields[].key. */
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  /**
   * Pending capability asset uploads (outer key = capability id, inner key =
   * AssetSlot.key, #1903). Non-empty → the caller must use the multipart
   * `with-assets` save endpoints so the files travel INSIDE the atomic save.
   * Only files for ACTIVE capabilities are included.
   */
  capabilityAssetFiles: Record<string, Record<string, File>>;
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
  /** Normalised names of the team's other agents (see agentNames.ts). */
  takenNames?: ReadonlySet<string>;
};

type FormState = {
  templateId: string;
  displayName: string;
  role: string;
  description: string;
  usageStatement: string;
  recommendedChatProfileId: string | null;
  tuningValues: Record<string, unknown>;
  selectedCapabilityIds: string[];
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  /** Pending capability asset files (capability id → AssetSlot.key → File, #1903). */
  capabilityAssetFiles: Record<string, Record<string, File | undefined>>;
  /** Save-blocking problems reported by capability config widgets (null = none). */
  capabilityBlockingErrors: Record<string, string | null>;
};

/** Mirrors AgentFormBody's routeField — only "Prompts" gets its own tab, everything else lands in "general". */
function sectionOfField(field: ManagedAgentFieldSpec): SectionKey {
  const g = (field.ui?.group ?? "").toLowerCase().trim();
  return g === "prompts" ? "prompts" : "general";
}

/** Selectable capabilities require explicit activation; fixed dependencies stay visible. */
export function defaultCapabilitySelection(template: AgentTemplateSummary | undefined): string[] {
  return template?.supports_capabilities ? [] : (template?.default_capability_ids ?? []);
}

/** Tuning values a NEW instance of `template` starts with, in the UI language. */
function defaultTuningValues(template: AgentTemplateSummary | undefined, lang: string): Record<string, unknown> {
  return Object.fromEntries(
    ((template?.default_tuning_fields ?? []) as ManagedAgentFieldSpec[])
      .filter((f) => f.default_by_lang?.[lang] != null || (f.default !== null && f.default !== undefined))
      .map((f) => [f.key, f.default_by_lang?.[lang] ?? f.default]),
  );
}

/**
 * Keep saved tuning and selections intact. The page sends only changed fields
 * on edit, including when a catalog no longer exposes a saved capability.
 */
export function buildAgentFormSubmitPayload(
  form: FormState,
  selectedTemplate: AgentTemplateSummary | undefined,
): AgentFormPayload {
  return {
    templateId: form.templateId,
    displayName: form.displayName.trim(),
    role: form.role,
    description: form.description,
    usageStatement: form.usageStatement,
    recommendedChatProfileId: form.recommendedChatProfileId,
    tuningFieldValues: form.tuningValues,
    selectedCapabilityIds: form.selectedCapabilityIds,
    capabilityConfigValues: form.capabilityConfigValues,
    capabilityAssetFiles: {},
    templateHasCapabilities: (selectedTemplate?.available_capabilities.length ?? 0) > 0,
  };
}

/**
 * Unwraps the persisted per-capability `{schema_version, config}` envelopes into
 * the flat `{ [capabilityId]: config }` shape the edit form renders and mutates.
 * Saved envelopes are preserved by omission in metadata PATCH requests.
 */
export function extractCapabilityConfigValues(
  storedConfig: ManagedAgentInstanceSummary["capability_config"],
): Record<string, Record<string, unknown>> {
  if (!storedConfig) return {};
  return Object.fromEntries(
    Object.entries(storedConfig).map(([id, envelope]) => {
      const config = (envelope as { config?: Record<string, unknown> })?.config ?? {};
      return [id, config];
    }),
  );
}

const NO_NAMES: ReadonlySet<string> = new Set();

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
  takenNames = NO_NAMES,
}: AgentFormModalProps) {
  const { t, i18n } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();

  // step 1 = choose template, step 2 = configure. Edit mode always starts at 2.
  const [step, setStep] = useState<1 | 2>(1);

  const [form, setForm] = useState<FormState>({
    templateId: "",
    displayName: "",
    role: "",
    description: "",
    usageStatement: "",
    recommendedChatProfileId: null,
    tuningValues: {},
    selectedCapabilityIds: [],
    capabilityConfigValues: {},
    capabilityAssetFiles: {},
    capabilityBlockingErrors: {},
  });
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [activeSection, setActiveSection] = useState<SectionKey>("general");
  // The name is checked when the field is left, never while typing; a name the
  // form filled in itself (template, edited agent) counts as checked.
  const [nameChecked, setNameChecked] = useState(false);

  useEffect(() => {
    setNameChecked(isOpen);
    if (!isOpen) {
      setSubmitAttempted(false);
      setActiveSection("general");
      return;
    }
    if (mode === "edit" && editInstance) {
      setForm({
        templateId: editInstance.template_id,
        displayName: editInstance.display_name,
        role: editInstance.role,
        description: editInstance.description ?? "",
        usageStatement: editInstance.usage_statement ?? "",
        recommendedChatProfileId: editInstance.recommended_chat_profile_id ?? null,
        tuningValues: (editInstance.tuning_field_values as Record<string, unknown>) ?? {},
        selectedCapabilityIds: editInstance.selected_capability_ids ?? [],
        // capability_config stores the {schema_version, config} envelope per id;
        // the form edits the inner `config` object only.
        capabilityConfigValues: extractCapabilityConfigValues(editInstance.capability_config),
        capabilityAssetFiles: {},
        capabilityBlockingErrors: {},
      });
      setStep(2);
    } else {
      setForm({
        templateId: "",
        displayName: "",
        role: "",
        description: "",
        usageStatement: "",
        recommendedChatProfileId: null,
        tuningValues: {},
        selectedCapabilityIds: [],
        capabilityConfigValues: {},
        capabilityAssetFiles: {},
        capabilityBlockingErrors: {},
      });
      setStep(1);
    }
  }, [isOpen, mode, editInstance]);

  const handleTemplateSelect = (id: string) => {
    const tpl = templates.find((t) => t.template_id === id);
    const lang = i18n.language.split("-")[0];
    setForm({
      templateId: id,
      displayName: tpl?.display_name ?? "",
      role: "",
      description: tpl?.description_by_lang?.[lang] ?? tpl?.description ?? "",
      usageStatement: "",
      recommendedChatProfileId: null,
      tuningValues: defaultTuningValues(tpl, lang),
      selectedCapabilityIds: defaultCapabilitySelection(tpl),
      capabilityConfigValues: {},
      capabilityAssetFiles: {},
      capabilityBlockingErrors: {},
    });
    setActiveSection("general");
    setSubmitAttempted(false);
    setNameChecked(true);
    setStep(2);
  };

  const handleTuningChange = (key: string, value: unknown) => {
    setForm((prev) => ({ ...prev, tuningValues: { ...prev.tuningValues, [key]: value } }));
  };

  const handleCapabilityConfigChange = (capabilityId: string, key: string, value: unknown) => {
    if (capabilityId === CAP_DOCUMENT_ACCESS) {
      setForm((prev) => ({ ...prev, ...applyDocumentAccessConfigChange(prev, key, value) }));
      return;
    }
    setForm((prev) => ({
      ...prev,
      capabilityConfigValues: {
        ...prev.capabilityConfigValues,
        [capabilityId]: { ...prev.capabilityConfigValues[capabilityId], [key]: value },
      },
    }));
  };

  const handleCapabilityAssetFileChange = (capabilityId: string, slotKey: string, file: File | null) => {
    setForm((prev) => ({
      ...prev,
      capabilityAssetFiles: {
        ...prev.capabilityAssetFiles,
        [capabilityId]: { ...prev.capabilityAssetFiles[capabilityId], [slotKey]: file ?? undefined },
      },
    }));
  };

  const handleCapabilityBlockingErrorChange = (capabilityId: string, message: string | null) => {
    setForm((prev) =>
      prev.capabilityBlockingErrors[capabilityId] === message
        ? prev
        : {
            ...prev,
            capabilityBlockingErrors: { ...prev.capabilityBlockingErrors, [capabilityId]: message },
          },
    );
  };

  const selectedTemplate = templates.find((tpl) => tpl.template_id === form.templateId);
  const validateTuning =
    mode === "create" || hasTuningChanges(form.tuningValues, editInstance?.tuning_field_values ?? {});
  const requiredFields = ((selectedTemplate?.default_tuning_fields ?? []) as ManagedAgentFieldSpec[]).filter(
    (f) => validateTuning && f.required && !f.ui?.hide,
  );
  const missingRequired = requiredFields.some(
    (f) =>
      form.tuningValues[f.key] === undefined || form.tuningValues[f.key] === null || form.tuningValues[f.key] === "",
  );
  // Mirrors the backend's 422 on reserved system-prompt tags (AgentFormBody
  // shows the message under the field); saving would only bounce.
  const reservedTagFields = ((selectedTemplate?.default_tuning_fields ?? []) as ManagedAgentFieldSpec[]).filter(
    (f) => validateTuning && !f.ui?.hide && reservedTagInPromptField(f, form.tuningValues[f.key]) !== null,
  );
  const nameTaken = nameChecked && isAgentNameTaken(form.displayName, takenNames);
  const recommendedChatProfileId = form.recommendedChatProfileId;
  const isFormValid =
    !!form.templateId &&
    !!form.displayName.trim() &&
    !!form.usageStatement.trim() &&
    !missingRequired &&
    reservedTagFields.length === 0 &&
    !nameTaken;
  const canSave = isFormValid && !isSubmitting;

  // Every section holding a blocking problem, computed once: the tab badges
  // (after a submit attempt) and the tab the failed submit jumps to read it.
  const sectionsWithErrors = new Set<SectionKey>([
    ...requiredFields
      .filter(
        (f) =>
          form.tuningValues[f.key] === undefined ||
          form.tuningValues[f.key] === null ||
          form.tuningValues[f.key] === "",
      )
      .map((f) => sectionOfField(f)),
    ...reservedTagFields.map((f) => sectionOfField(f)),
    ...(!form.displayName.trim() || nameTaken ? (["general"] as const) : []),
    ...(!form.usageStatement.trim() ? (["commitments"] as const) : []),
  ]);
  const errorSections = submitAttempted ? sectionsWithErrors : new Set<SectionKey>();

  const handleSubmit = async () => {
    setSubmitAttempted(true);
    if (!canSave) {
      const firstErrorSection = (["general", "prompts", "tools", "commitments"] as const).find((s) =>
        sectionsWithErrors.has(s),
      );
      if (firstErrorSection) setActiveSection(firstErrorSection);
      return;
    }
    await onSubmit(buildAgentFormSubmitPayload({ ...form, recommendedChatProfileId }, selectedTemplate));
  };

  const assistantButton = (
    <Button
      color="primary"
      variant="tonal"
      size="small"
      icon={{ category: "outlined", type: "auto_awesome" }}
      className={styles.assistantButton}
      title={t("rework.weaverAgents.notConnected")}
      disabled
    >
      {t("rework.teams.formAgent.creationAssistant.open")}
    </Button>
  );

  const title =
    mode === "edit"
      ? t("rework.teams.formAgent.titleEdit", { agent: editInstance?.display_name ?? "" })
      : t("rework.teams.formAgent.titleCreate", { agentsNicknameSingular });

  const teamLabel = teamName || t("rework.sidebar.team.userTeam");
  const subtitle = selectedTemplate
    ? t("rework.teams.formAgent.subtitleWithTemplate", { team: teamLabel, template: selectedTemplate.display_name })
    : t("rework.teams.formAgent.subtitle", { team: teamLabel });

  return (
    <SettingsModal
      isOpen={isOpen}
      onClose={onClose}
      id="agent-form-modal"
      cardClassName={styles.card}
      title={title}
      subtitle={subtitle}
      actions={
        <>
          {/* Not on the template step: the assistant cannot pick a template from a description yet. */}
          {step === 2 && selectedTemplate && assistantButton}
          <Button color="primary" variant="outlined" size="medium" onClick={onClose}>
            {t("rework.cancel")}
          </Button>
          {step === 2 && (
            <Button
              color={submitAttempted && !isFormValid ? "warning" : "primary"}
              variant="filled"
              size="medium"
              disabled={nameTaken || isSubmitting}
              onClick={handleSubmit}
            >
              {mode === "edit" ? t("rework.save") : t("rework.create")}
            </Button>
          )}
        </>
      }
      footer={
        mode === "edit" && onDelete ? (
          <Button color="error" variant="outlined" size="medium" onClick={onDelete}>
            {t("rework.delete")}
          </Button>
        ) : undefined
      }
    >
      {step === 1 ? (
        <TemplateBrowser templates={templates} selectedId={form.templateId} onSelect={handleTemplateSelect} />
      ) : (
        <AgentFormBody
          mode={mode}
          templates={templates}
          templateId={form.templateId}
          displayName={form.displayName}
          role={form.role}
          description={form.description}
          usageStatement={form.usageStatement}
          recommendedChatProfileId={recommendedChatProfileId}
          tuningFieldValues={form.tuningValues}
          selectedCapabilityIds={form.selectedCapabilityIds}
          capabilityConfigValues={form.capabilityConfigValues}
          capabilityAssetFiles={form.capabilityAssetFiles}
          isSubmitting={isSubmitting}
          submitAttempted={submitAttempted}
          activeSection={activeSection}
          onSectionChange={setActiveSection}
          errorSections={errorSections}
          editInstance={editInstance}
          teamId={teamId}
          nameTaken={nameTaken}
          onDisplayNameChange={(v) => {
            setForm((prev) => ({ ...prev, displayName: v }));
            setNameChecked(false);
          }}
          onDisplayNameBlur={() => setNameChecked(true)}
          onRoleChange={(v) => setForm((prev) => ({ ...prev, role: v }))}
          onDescriptionChange={(v) => setForm((prev) => ({ ...prev, description: v }))}
          onUsageStatementChange={(v) => setForm((prev) => ({ ...prev, usageStatement: v }))}
          onRecommendedChatProfileIdChange={(v) => setForm((prev) => ({ ...prev, recommendedChatProfileId: v }))}
          onTuningChange={handleTuningChange}
          onCapabilitySelectionChange={(ids) => setForm((prev) => ({ ...prev, selectedCapabilityIds: ids }))}
          onCapabilitySelectionReplace={(next) =>
            setForm((prev) => ({
              ...prev,
              selectedCapabilityIds: next.selectedCapabilityIds,
              capabilityConfigValues: next.capabilityConfigValues,
            }))
          }
          onCapabilityConfigChange={handleCapabilityConfigChange}
          onCapabilityAssetFileChange={handleCapabilityAssetFileChange}
          onCapabilityBlockingErrorChange={handleCapabilityBlockingErrorChange}
        />
      )}
    </SettingsModal>
  );
}
