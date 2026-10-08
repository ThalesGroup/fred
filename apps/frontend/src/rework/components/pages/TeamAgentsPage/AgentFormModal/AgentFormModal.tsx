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
  ManagedAgentFieldSpec,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { AgentFormBody, type SectionKey } from "./AgentFormBody.tsx";
import { CreationAssistantDialog } from "./CreationAssistantDialog/CreationAssistantDialog.tsx";
import {
  type AppliedDraft,
  applyRecommendedCapabilities,
  type DraftTargets,
  findSystemPromptField,
  isReasoningOffered,
} from "./CreationAssistantDialog/creationAssistant.ts";
import styles from "./AgentFormModal.module.css";
import { TemplateBrowser } from "./TemplateBrowser/TemplateBrowser.tsx";
import { applyDocumentAccessConfigChange, normalizeDocumentAccessConfig } from "./toolPackLogic.ts";
import { CAP_DOCUMENT_ACCESS } from "./toolPacks.ts";
import { reservedTagInPromptField } from "@rework/utils/promptValidation";

export type AgentFormPayload = {
  templateId: string;
  displayName: string;
  role: string;
  description: string;
  usageStatement: string;
  /** REASON-01 level 3: does this agent offer the composer's reasoning toggle? */
  reasoningEnabled: boolean;
  /**
   * REASON-01 Amendment B: does a new conversation start with that toggle
   * already on? Always submitted, including while `reasoningEnabled` is false —
   * the value is then inert backend-side, which is what lets an author withdraw
   * the offer and restore it later without losing their default.
   */
  reasoningDefaultOn: boolean;
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
};

type FormState = {
  templateId: string;
  displayName: string;
  role: string;
  description: string;
  usageStatement: string;
  reasoningEnabled: boolean;
  reasoningDefaultOn: boolean;
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

/**
 * The capability ids `template` advertises to THIS team.
 *
 * Server-side, `available_capabilities` is already filtered to what the team
 * `can_use` (CAPAB-01), so this set doubles as the authorization boundary: an
 * admin-gated capability the team is not enabled for is simply absent. Both
 * the default seeding and the submit payload narrow through it, so the two
 * cannot drift apart.
 */
function advertisedCapabilityIds(template: AgentTemplateSummary | undefined): Set<string> {
  return new Set((template?.available_capabilities ?? []).map((cap) => cap.id));
}

/**
 * The capabilities a NEW instance of `template` starts with ticked: its
 * declared defaults, narrowed to what it advertises to this team.
 *
 * Because `advertisedCapabilityIds` is already `can_use`-filtered, a default
 * the team is not enabled for is neither seeded nor rendered — there is no
 * pre-ticked box the save would 403 on, and no second authorization signal is
 * needed on the wire.
 *
 * Why this exists at all: the form always submits an explicit `capability_ids`
 * for a template that has capabilities, and the backend reads an explicit `[]`
 * as "none" — which bypasses its own template-default path. Seeding here is
 * what makes a template's declared defaults actually reach a new instance.
 */
export function defaultCapabilitySelection(template: AgentTemplateSummary | undefined): string[] {
  const advertised = advertisedCapabilityIds(template);
  return (template?.default_capability_ids ?? []).filter((capabilityId) => advertised.has(capabilityId));
}

/**
 * The reasoning settings a NEW instance of `template` starts with (#2473):
 * whether its Reasoning card is pre-ticked (REASON-01 level 3) and whether the
 * nested "start conversations in Boost" switch is pre-set (Amendment B).
 *
 * Deliberately NOT narrowed by platform state, mirroring the card it seeds.
 * The Reasoning card is rendered unconditionally in `AgentFormBody` and the
 * form never reads `reasoning_enabled_model_ids`; levels 1-2 are enforced live
 * on the send path, where an agent that offers reasoning on a deployment with
 * no reasoning-enabled model simply gets no composer control. Suppressing the
 * pre-tick here instead would make it vanish based on platform state invisible
 * from this form — the "I turned it on and nothing happened" confusion the
 * absent-not-inert rule exists to prevent.
 *
 * A seed, not a lock: the operator can untick either before saving, and both
 * are submitted explicitly on create, so this is what makes a template's
 * declared reasoning defaults actually reach a new instance.
 */
export function defaultReasoningSelection(template: AgentTemplateSummary | undefined): {
  reasoningEnabled: boolean;
  reasoningDefaultOn: boolean;
} {
  return {
    reasoningEnabled: template?.reasoning_enabled ?? false,
    reasoningDefaultOn: template?.reasoning_default_on ?? false,
  };
}

/** Tuning values a NEW instance of `template` starts with, in the UI language. */
function defaultTuningValues(template: AgentTemplateSummary | undefined, lang: string): Record<string, unknown> {
  return Object.fromEntries(
    (template?.default_tuning_fields ?? [])
      .filter((f) => f.default_by_lang?.[lang] != null || (f.default !== null && f.default !== undefined))
      .map((f) => [f.key, f.default_by_lang?.[lang] ?? f.default]),
  );
}

/**
 * What the creation assistant would replace. On create, a value still equal to
 * the template's seed counts as empty: the user did not write it, so replacing
 * it needs no confirmation. On edit, every value is the saved agent's.
 */
export function draftTargets(
  form: Pick<
    FormState,
    "displayName" | "role" | "description" | "tuningValues" | "selectedCapabilityIds" | "capabilityConfigValues"
  >,
  template: AgentTemplateSummary | undefined,
  lang: string,
  promptKey: string | undefined,
  mode: "create" | "edit",
): DraftTargets {
  const unlessSeed = (value: string, seed: string | undefined) =>
    mode === "create" && value.trim() === (seed ?? "").trim() ? "" : value;
  const seedPrompt = promptKey ? defaultTuningValues(template, lang)[promptKey] : undefined;
  const prompt = promptKey ? String(form.tuningValues[promptKey] ?? "") : "";
  const seedCapabilities = defaultCapabilitySelection(template);
  const sameAsSeed =
    mode === "create" &&
    form.selectedCapabilityIds.length === seedCapabilities.length &&
    seedCapabilities.every((id) => form.selectedCapabilityIds.includes(id));
  return {
    name: unlessSeed(form.displayName, template?.display_name),
    role: form.role,
    description: unlessSeed(form.description, template?.description_by_lang?.[lang] ?? template?.description ?? ""),
    systemPrompt: unlessSeed(prompt, seedPrompt === undefined || seedPrompt === null ? "" : String(seedPrompt)),
    capabilityIds: sameAsSeed ? [] : form.selectedCapabilityIds,
    capabilityConfigValues: form.capabilityConfigValues,
  };
}

/**
 * Builds the submit payload using the selected template contract so stale
 * capability keys from previous UI versions cannot leak into create or edit
 * requests.
 */
export function buildAgentFormSubmitPayload(
  form: FormState,
  selectedTemplate: AgentTemplateSummary | undefined,
): AgentFormPayload {
  // Only active capabilities are advertised by the template; drop selections and
  // config slices for ids the template no longer exposes, and for capabilities
  // that are not currently ticked, so deselected config never reaches the pod.
  const availableCapabilityIds = advertisedCapabilityIds(selectedTemplate);
  const effectiveCapabilityIds = form.selectedCapabilityIds.filter((id) => availableCapabilityIds.has(id));
  const effectiveCapabilityConfig = Object.fromEntries(
    Object.entries(form.capabilityConfigValues).filter(([id]) => effectiveCapabilityIds.includes(id)),
  );
  // Asset files only travel for ACTIVE capabilities, with undefined slots
  // dropped, so a deselected capability's staged upload never reaches the pod.
  const effectiveAssetFiles = Object.fromEntries(
    Object.entries(form.capabilityAssetFiles)
      .filter(([id]) => effectiveCapabilityIds.includes(id))
      .map(([id, slots]) => [
        id,
        Object.fromEntries(Object.entries(slots).filter(([, file]) => file instanceof File)) as Record<string, File>,
      ])
      .filter(([, slots]) => Object.keys(slots).length > 0),
  );

  return {
    templateId: form.templateId,
    displayName: form.displayName.trim(),
    role: form.role.trim(),
    description: form.description.trim(),
    usageStatement: form.usageStatement.trim(),
    reasoningEnabled: form.reasoningEnabled,
    reasoningDefaultOn: form.reasoningDefaultOn,
    tuningFieldValues: form.tuningValues,
    selectedCapabilityIds: effectiveCapabilityIds,
    capabilityConfigValues: effectiveCapabilityConfig,
    capabilityAssetFiles: effectiveAssetFiles,
    templateHasCapabilities: availableCapabilityIds.size > 0,
  };
}

/**
 * Unwraps the persisted per-capability `{schema_version, config}` envelopes into
 * the flat `{ [capabilityId]: config }` shape the edit form renders and mutates.
 * Legacy `document_access` keys are read as its two sources.
 */
export function extractCapabilityConfigValues(
  storedConfig: ManagedAgentInstanceSummary["capability_config"],
): Record<string, Record<string, unknown>> {
  if (!storedConfig) return {};
  return Object.fromEntries(
    Object.entries(storedConfig).map(([id, envelope]) => {
      const config = (envelope as { config?: Record<string, unknown> })?.config ?? {};
      return [id, id === CAP_DOCUMENT_ACCESS ? normalizeDocumentAccessConfig(config) : config];
    }),
  );
}

/** Turning reasoning on also turns it on by default for new conversations;
 *  the member can still untick that afterwards. */
export function withReasoning(
  prev: Pick<FormState, "reasoningEnabled" | "reasoningDefaultOn">,
  enabled: boolean,
): Pick<FormState, "reasoningEnabled" | "reasoningDefaultOn"> {
  const turnedOn = enabled && !prev.reasoningEnabled;
  return { reasoningEnabled: enabled, reasoningDefaultOn: turnedOn || prev.reasoningDefaultOn };
}

/** Save-blocking problems reported by config widgets. Only ACTIVE capabilities count. */
function isCapabilityBlocked(form: Pick<FormState, "selectedCapabilityIds" | "capabilityBlockingErrors">): boolean {
  return form.selectedCapabilityIds.some((id) => !!form.capabilityBlockingErrors[id]);
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
  const { agentsNicknameSingular } = useFrontendProperties();

  // step 1 = choose template, step 2 = configure. Edit mode always starts at 2.
  const [step, setStep] = useState<1 | 2>(1);

  const [form, setForm] = useState<FormState>({
    templateId: "",
    displayName: "",
    role: "",
    description: "",
    usageStatement: "",
    reasoningEnabled: false,
    reasoningDefaultOn: false,
    tuningValues: {},
    selectedCapabilityIds: [],
    capabilityConfigValues: {},
    capabilityAssetFiles: {},
    capabilityBlockingErrors: {},
  });
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [activeSection, setActiveSection] = useState<SectionKey>("general");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [draftRevision, setDraftRevision] = useState(0);

  useEffect(() => {
    if (!isOpen) {
      setSubmitAttempted(false);
      setActiveSection("general");
      setAssistantOpen(false);
      return;
    }
    if (mode === "edit" && editInstance) {
      setForm({
        templateId: editInstance.template_id,
        displayName: editInstance.display_name,
        role: editInstance.role,
        description: editInstance.description ?? "",
        usageStatement: editInstance.usage_statement ?? "",
        reasoningEnabled: editInstance.reasoning_enabled ?? false,
        reasoningDefaultOn: editInstance.reasoning_default_on ?? false,
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
        reasoningEnabled: false,
        reasoningDefaultOn: false,
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
      // #2473: seeded from the template like `selectedCapabilityIds` below,
      // instead of the hardcoded `false` pair that made a template's declared
      // reasoning defaults unreachable.
      ...defaultReasoningSelection(tpl),
      tuningValues: defaultTuningValues(tpl, lang),
      selectedCapabilityIds: defaultCapabilitySelection(tpl),
      capabilityConfigValues: {},
      capabilityAssetFiles: {},
      capabilityBlockingErrors: {},
    });
    setActiveSection("general");
    setSubmitAttempted(false);
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
  const requiredFields = (selectedTemplate?.default_tuning_fields ?? []).filter((f) => f.required && !f.ui?.hide);
  const missingRequired = requiredFields.some((f) => !form.tuningValues[f.key]);
  // Mirrors the backend's 422 on reserved system-prompt tags (AgentFormBody
  // shows the message under the field); saving would only bounce.
  const reservedTagFields = (selectedTemplate?.default_tuning_fields ?? []).filter(
    (f) => !f.ui?.hide && reservedTagInPromptField(f, form.tuningValues[f.key]) !== null,
  );
  // A capability config widget may block the save (e.g. ppt_filler while its
  // mandatory template is missing, #1903) — only ACTIVE capabilities count.
  const capabilityBlocked = isCapabilityBlocked(form);
  const isFormValid =
    !!form.templateId &&
    !!form.displayName.trim() &&
    !!form.usageStatement.trim() &&
    !missingRequired &&
    reservedTagFields.length === 0 &&
    !capabilityBlocked;
  const canSave = isFormValid && !isSubmitting;

  // Every section holding a blocking problem, computed once: the tab badges
  // (after a submit attempt) and the tab the failed submit jumps to read it.
  const sectionsWithErrors = new Set<SectionKey>([
    ...requiredFields.filter((f) => !form.tuningValues[f.key]).map((f) => sectionOfField(f)),
    ...reservedTagFields.map((f) => sectionOfField(f)),
    ...(!form.displayName.trim() ? (["general"] as const) : []),
    ...(capabilityBlocked ? (["tools"] as const) : []),
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
    await onSubmit(buildAgentFormSubmitPayload(form, selectedTemplate));
  };

  // The assistant drafts the template's main prompt field and picks among the
  // capabilities the template advertises to this team.
  const lang = i18n.language.split("-")[0];
  const promptField = findSystemPromptField((selectedTemplate?.default_tuning_fields ?? []).filter((f) => !f.ui?.hide));
  const templateCapabilities = selectedTemplate?.available_capabilities ?? [];
  const assistantReady = !!selectedTemplate && !!teamId;

  const applyDraft = (draft: AppliedDraft) => {
    setForm((prev) => {
      const next = { ...prev };
      if (draft.name !== undefined) next.displayName = draft.name;
      if (draft.role !== undefined) next.role = draft.role;
      if (draft.description !== undefined) next.description = draft.description;
      if (draft.systemPrompt !== undefined && promptField) {
        next.tuningValues = { ...prev.tuningValues, [promptField.key]: draft.systemPrompt };
      }
      if (draft.capabilityIds) {
        Object.assign(
          next,
          applyRecommendedCapabilities(
            draft.capabilityIds,
            {
              selectedCapabilityIds: prev.selectedCapabilityIds,
              capabilityConfigValues: prev.capabilityConfigValues,
              reasoningEnabled: prev.reasoningEnabled,
            },
            advertisedCapabilityIds(selectedTemplate),
          ),
        );
      }
      // Last and on `next`: the capability step carries the old reasoningEnabled,
      // and merging from prev would copy every other old field back.
      return draft.reasoning ? { ...next, ...withReasoning(next, true) } : next;
    });
    setDraftRevision((revision) => revision + 1);
    setAssistantOpen(false);
  };

  const assistantButton = (
    <Button
      color="primary"
      variant="tonal"
      size="small"
      icon={{ category: "outlined", type: "auto_awesome" }}
      className={styles.assistantButton}
      onClick={() => setAssistantOpen(true)}
      disabled={!assistantReady || isSubmitting}
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
          reasoningEnabled={form.reasoningEnabled}
          reasoningDefaultOn={form.reasoningDefaultOn}
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
          onDisplayNameChange={(v) => setForm((prev) => ({ ...prev, displayName: v }))}
          onRoleChange={(v) => setForm((prev) => ({ ...prev, role: v }))}
          onDescriptionChange={(v) => setForm((prev) => ({ ...prev, description: v }))}
          onUsageStatementChange={(v) => setForm((prev) => ({ ...prev, usageStatement: v }))}
          onReasoningEnabledChange={(v) => setForm((prev) => ({ ...prev, ...withReasoning(prev, v) }))}
          onReasoningDefaultOnChange={(v) => setForm((prev) => ({ ...prev, reasoningDefaultOn: v }))}
          onTuningChange={handleTuningChange}
          onCapabilitySelectionChange={(ids) => setForm((prev) => ({ ...prev, selectedCapabilityIds: ids }))}
          onCapabilitySelectionReplace={(next) =>
            setForm((prev) => ({
              ...prev,
              selectedCapabilityIds: next.selectedCapabilityIds,
              capabilityConfigValues: next.capabilityConfigValues,
              ...withReasoning(prev, next.reasoningEnabled),
            }))
          }
          onCapabilityConfigChange={handleCapabilityConfigChange}
          onCapabilityAssetFileChange={handleCapabilityAssetFileChange}
          onCapabilityBlockingErrorChange={handleCapabilityBlockingErrorChange}
          draftRevision={draftRevision}
        />
      )}
      {assistantReady && teamId && (
        <CreationAssistantDialog
          open={assistantOpen}
          teamId={teamId}
          templateId={form.templateId}
          capabilities={templateCapabilities}
          hasPromptField={!!promptField}
          offersReasoning={isReasoningOffered(advertisedCapabilityIds(selectedTemplate))}
          current={draftTargets(form, selectedTemplate, lang, promptField?.key, mode)}
          onApply={applyDraft}
          onClose={() => setAssistantOpen(false)}
        />
      )}
    </SettingsModal>
  );
}
