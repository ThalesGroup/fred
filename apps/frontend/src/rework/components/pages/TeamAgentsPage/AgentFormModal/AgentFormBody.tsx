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

import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import type {
  CapabilityCatalogEntry,
  FieldSpec as ManagedAgentFieldSpec,
} from "../../../../../slices/runtime/runtimeOpenApi";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { reservedTagInPromptField } from "@rework/utils/promptValidation";
import { TuningFieldRenderer } from "./TuningFieldRenderer.tsx";
import { CapabilityCard } from "./CapabilityCard/CapabilityCard.tsx";
import { SimpleCapabilitiesView } from "./SimpleCapabilitiesView/SimpleCapabilitiesView.tsx";
import type { CapabilitySelectionState } from "./toolPackLogic.ts";

import { helpPagePath } from "@rework/features/helpCenter/content";
import { isHelpLang } from "@rework/features/helpCenter/manifest";
import styles from "./AgentFormBody.module.css";

export type SectionKey = "general" | "prompts" | "tools" | "commitments";

const SECTION_ORDER: SectionKey[] = ["general", "prompts", "tools", "commitments"];

const SECTION_LABEL_KEYS: Record<SectionKey, string> = {
  general: "rework.teams.formAgent.sections.general",
  prompts: "rework.teams.formAgent.sections.prompts",
  tools: "rework.teams.formAgent.sections.tools",
  commitments: "rework.teams.formAgent.sections.commitments",
};

const SECTION_ICONS: Record<SectionKey, { category: "outlined"; type: IconType }> = {
  general: { category: "outlined", type: "tune" },
  prompts: { category: "outlined", type: "edit_note" },
  tools: { category: "outlined", type: "build" },
  commitments: { category: "outlined", type: "shield" },
};

/**
 * Only `ui.group === "Prompts"` gets its own tab; every other declared group
 * (Settings, Credentials, Document reading, Mindmap, Grounding, Comparison,
 * Fallback, ...) folds into "General" alongside name/role/description. This
 * keeps the 4-tab layout compatible with the existing template `ui.group`
 * taxonomy without requiring any template-side changes.
 */
function routeField(field: ManagedAgentFieldSpec): "prompts" | "general" {
  const g = (field.ui?.group ?? "").toLowerCase().trim();
  return g === "prompts" ? "prompts" : "general";
}

function formatRelativeDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 30) return `${diffDays} days ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths === 1) return "1 month ago";
  if (diffMonths < 12) return `${diffMonths} months ago`;
  return `${Math.floor(diffMonths / 12)} year(s) ago`;
}

type AgentFormBodyProps = {
  mode: "create" | "edit";
  templates: AgentTemplateSummary[];
  templateId: string;
  displayName: string;
  role: string;
  description: string;
  usageStatement: string;
  /** Retained legacy reference for display only; never a model resolution key. */
  recommendedChatProfileId: string | null;
  tuningFieldValues: Record<string, unknown>;
  /** Explicit list of active capability ids ([] = none active). */
  selectedCapabilityIds: string[];
  /** Per-capability config values: outer key = capability id, inner key = config_fields[].key. */
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  /** Pending capability asset files: outer key = capability id, inner key = AssetSlot.key (#1903). */
  capabilityAssetFiles: Record<string, Record<string, File | undefined>>;
  isSubmitting: boolean;
  submitAttempted: boolean;
  activeSection: SectionKey;
  onSectionChange: (s: SectionKey) => void;
  errorSections: Set<SectionKey>;
  editInstance?: ManagedAgentInstanceSummary;
  teamId?: string;
  /** Another agent of the team has this name; shown once the name field was left. */
  nameTaken?: boolean;
  onDisplayNameChange: (v: string) => void;
  onDisplayNameBlur?: () => void;
  onRoleChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onUsageStatementChange: (v: string) => void;
  onRecommendedChatProfileIdChange: (v: string | null) => void;
  onTuningChange: (key: string, value: unknown) => void;
  onCapabilitySelectionChange: (ids: string[]) => void;
  /** Atomic replacement of the whole capability selection (ids + config) —
   *  used by the Simple "packs" view, which flips several at once. */
  onCapabilitySelectionReplace: (next: CapabilitySelectionState) => void;
  onCapabilityConfigChange: (capabilityId: string, key: string, value: unknown) => void;
  onCapabilityAssetFileChange: (capabilityId: string, slotKey: string, file: File | null) => void;
  onCapabilityBlockingErrorChange: (capabilityId: string, message: string | null) => void;
  /** Bumped when the creation assistant fills the form: prompt fields show the editor again. */
  draftRevision?: number;
};

export function AgentFormBody({
  mode,
  templates,
  templateId,
  displayName,
  role,
  description,
  usageStatement,
  recommendedChatProfileId,
  tuningFieldValues,
  selectedCapabilityIds,
  capabilityConfigValues,
  isSubmitting,
  submitAttempted,
  activeSection,
  onSectionChange,
  errorSections,
  editInstance,
  teamId,
  nameTaken = false,
  onDisplayNameChange,
  onDisplayNameBlur,
  onRoleChange,
  onDescriptionChange,
  onUsageStatementChange,
  onTuningChange,
  onCapabilitySelectionChange,
  onCapabilitySelectionReplace,
  draftRevision = 0,
}: AgentFormBodyProps) {
  const { t, i18n } = useTranslation();
  const uiLang = i18n.language.split("-")[0];
  const helpLang = isHelpLang(uiLang) ? uiLang : "fr";
  // Simple = new "capability packs" view (default); Advanced = the flat
  // per-capability list. UI-only, reset to Simple on each mount (#2220).
  const [capabilityView, setCapabilityView] = useState<"simple" | "advanced">("simple");

  // Prompt-picker mode per field key, kept here (this body stays mounted across
  // section switches) so a field the user emptied doesn't auto-reopen the
  // library when they leave and return to the Prompts section (#bug).
  const [promptPickerExplicit, setPromptPickerExplicit] = useState<Record<string, boolean | null>>({});
  useEffect(() => {
    if (draftRevision > 0) setPromptPickerExplicit({});
  }, [draftRevision]);

  const selectedTemplate = templates.find((tpl) => tpl.template_id === templateId);
  const templateMissing = mode === "edit" && !selectedTemplate;
  const capabilities = (selectedTemplate?.available_capabilities ?? []) as CapabilityCatalogEntry[];
  // False: `capabilities` are included with the agent, always on, only configured.
  const availableCapabilityIds = new Set(capabilities.map((item) => item.id));
  const supportsCapabilities = selectedTemplate?.supports_capabilities ?? true;

  const visibleFields = ((selectedTemplate?.default_tuning_fields ?? []) as ManagedAgentFieldSpec[]).filter(
    (f) => !f.ui?.hide,
  );
  const promptFields = visibleFields.filter((f) => routeField(f) === "prompts");
  const generalFields = visibleFields.filter((f) => routeField(f) === "general");

  const visibleSections = SECTION_ORDER.filter((s) => {
    if (s === "prompts") return promptFields.length > 0;
    return true; // general, tools and commitments always have content
  });

  const effectiveSection = visibleSections.includes(activeSection) ? activeSection : (visibleSections[0] ?? "general");
  const activeSectionIndex = Math.max(0, visibleSections.indexOf(effectiveSection));

  const nameError = nameTaken
    ? t("rework.teams.formAgent.fields.name.taken")
    : submitAttempted && !displayName.trim()
      ? t("rework.teams.formAgent.fields.name.label")
      : undefined;
  const usageStatementError =
    submitAttempted && !usageStatement.trim() ? t("rework.teams.formAgent.fields.usageStatement.label") : undefined;

  // Effective value (current input or declared default) of every tuning field,
  // across sections — drives `ui.visible_when` even when the gating field lives
  // in another section.
  const effectiveTuningValues = Object.fromEntries(
    (selectedTemplate?.default_tuning_fields ?? []).map((f) => [
      f.key,
      mode === "edit" ? tuningFieldValues[f.key] : (tuningFieldValues[f.key] ?? f.default),
    ]),
  );

  // A reserved system-prompt tag is refused by the backend (422) whichever way
  // it is submitted; say so while typing rather than after the round-trip.
  const fieldError = (field: ManagedAgentFieldSpec): string | undefined => {
    const value = tuningFieldValues[field.key];
    const reservedTag = reservedTagInPromptField(field, value);
    if (reservedTag) return t("rework.promptEditor.reservedTag", { tag: reservedTag });
    return submitAttempted && field.required && (value === undefined || value === null || value === "")
      ? `${field.title} is required`
      : undefined;
  };

  const renderFieldList = (fields: ManagedAgentFieldSpec[]) =>
    fields.map((field) => (
      <TuningFieldRenderer
        key={field.key}
        field={field}
        value={tuningFieldValues[field.key]}
        onChange={onTuningChange}
        disabled={isSubmitting}
        teamId={teamId}
        disconnected
        useDefaults={mode === "create"}
        allValues={effectiveTuningValues}
        pickerExplicit={promptPickerExplicit[field.key] ?? null}
        onPickerExplicitChange={(v) => setPromptPickerExplicit((prev) => ({ ...prev, [field.key]: v }))}
        error={fieldError(field)}
      />
    ));

  return (
    <div className={styles.body}>
      {/* Absorbs Chrome's username+password credential heuristic away from real form fields */}
      <input
        type="text"
        autoComplete="username"
        aria-hidden="true"
        className={styles.credentialHoneypot}
        tabIndex={-1}
        readOnly
      />
      <input
        type="password"
        autoComplete="new-password"
        aria-hidden="true"
        className={styles.credentialHoneypot}
        tabIndex={-1}
        readOnly
      />
      {templateMissing && (
        <p className={styles.templateUnavailableNotice}>{t("rework.teams.formAgent.templateUnavailable")}</p>
      )}

      {
        <>
          {errorSections.size > 0 && (
            <div className={styles.validationBanner} role="alert">
              {t("rework.teams.formAgent.validation.requiredFields")}
            </div>
          )}

          <div className={styles.tabStrip}>
            <div className={styles.tabGroup}>
              <ButtonGroup
                key={visibleSections.join(",")}
                size="small"
                color="secondary"
                variant="radio"
                fullWidth
                aria-label={t("rework.teams.formAgent.sections.aria")}
                selectedIndex={activeSectionIndex}
                onSelectedIndexChange={(i) => onSectionChange(visibleSections[i] as SectionKey)}
                items={visibleSections.map((s) => ({
                  label: t(SECTION_LABEL_KEYS[s]),
                  icon: SECTION_ICONS[s],
                  hasError: errorSections.has(s),
                  onClick: () => onSectionChange(s),
                }))}
              />
            </div>
          </div>

          <div className={styles.sectionContent}>
            {effectiveSection === "general" && (
              <>
                <div className={styles.fieldRow}>
                  <TextInput
                    label={t("rework.teams.formAgent.fields.name.label")}
                    value={displayName}
                    onChange={(e) => onDisplayNameChange(e.target.value)}
                    onBlur={onDisplayNameBlur}
                    maxLength={255}
                    required
                    disabled={isSubmitting}
                    error={nameError}
                  />
                  <TextInput
                    label={t("rework.teams.formAgent.fields.role.label")}
                    placeholder={displayName}
                    value={role}
                    onChange={(e) => onRoleChange(e.target.value)}
                    maxLength={255}
                    disabled={isSubmitting}
                  />
                </div>
                <TextArea
                  label={t("rework.teams.formAgent.fields.description.label")}
                  value={description}
                  onChange={(e) => onDescriptionChange(e.target.value)}
                  rows={3}
                  maxLength={500}
                  disabled={isSubmitting}
                />
                <TextInput
                  label={t("rework.weaverAgents.modelProfile")}
                  value={
                    editInstance?.recommended_model
                      ? `${editInstance.recommended_model.source_id} / ${editInstance.recommended_model.upstream_model_id}`
                      : (recommendedChatProfileId ?? "")
                  }
                  disabled
                  explanation={t(
                    recommendedChatProfileId && !editInstance?.recommended_model
                      ? "rework.weaverAgents.legacyModelReselection"
                      : "rework.weaverAgents.modelUnavailable",
                  )}
                />
                {renderFieldList(generalFields)}
              </>
            )}
            {effectiveSection === "prompts" && renderFieldList(promptFields)}
            {effectiveSection === "tools" && (
              <>
                <div className={styles.capabilitiesHeader}>
                  <div className={styles.capabilitiesTitleGroup}>
                    <h2 className={styles.capabilitiesTitle}>{t("rework.teams.formAgent.capabilities.header")}</h2>
                    <Link
                      className={styles.learnMoreLink}
                      to={helpPagePath(helpLang, "features", "capabilities")}
                      target="_blank"
                      rel="opener"
                    >
                      {t("rework.teams.formAgent.capabilities.learnMore")}
                    </Link>
                  </div>
                  <label className={styles.advancedToggle}>
                    <span>{t("rework.teams.formAgent.capabilities.viewToggle.advanced")}</span>
                    <Switch
                      size="small"
                      checked={capabilityView === "advanced"}
                      onChange={() => setCapabilityView(capabilityView === "advanced" ? "simple" : "advanced")}
                      disabled={isSubmitting}
                      aria-label={t("rework.teams.formAgent.capabilities.viewToggle.aria")}
                    />
                  </label>
                </div>
                <p>{t("rework.weaverAgents.capabilitiesUnavailable")}</p>
                {selectedCapabilityIds.length > 0 && <p>{selectedCapabilityIds.join(", ")}</p>}
                {capabilityView === "simple" ? (
                  <SimpleCapabilitiesView
                    availableIds={availableCapabilityIds}
                    supportsCapabilities={supportsCapabilities}
                    includedCapabilities={capabilities}
                    renderIncludedOptions={() => null}
                    selection={{ selectedCapabilityIds, capabilityConfigValues }}
                    disabled
                    onSelectionChange={onCapabilitySelectionReplace}
                    renderPackOptions={() => null}
                  />
                ) : (
                  <ul className={styles.toolsList}>
                    {capabilities.map((capability) => {
                      const name = t(capability.name, { defaultValue: capability.name });
                      const description = t(capability.description, { defaultValue: capability.description });
                      if (!supportsCapabilities) {
                        return (
                          <CapabilityCard
                            key={capability.id}
                            name={name}
                            description={description}
                            included
                            subForm={undefined}
                          />
                        );
                      }
                      const checked = selectedCapabilityIds.includes(capability.id);
                      const toggle = () => {
                        const next = checked
                          ? selectedCapabilityIds.filter((id) => id !== capability.id)
                          : [...selectedCapabilityIds, capability.id];
                        onCapabilitySelectionChange(next);
                      };
                      return (
                        <CapabilityCard
                          key={capability.id}
                          name={name}
                          description={description}
                          checked={checked}
                          disabled
                          onToggle={toggle}
                          subForm={undefined}
                        />
                      );
                    })}
                  </ul>
                )}
              </>
            )}
            {effectiveSection === "commitments" && (
              <>
                <p className={styles.commitmentsIntro}>{t("rework.teams.formAgent.fields.usageStatement.intro")}</p>
                <TextArea
                  label={t("rework.teams.formAgent.fields.usageStatement.label")}
                  placeholder={t("rework.teams.formAgent.fields.usageStatement.placeholder")}
                  value={usageStatement}
                  onChange={(e) => onUsageStatementChange(e.target.value)}
                  rows={8}
                  required
                  disabled={isSubmitting}
                  error={usageStatementError}
                />
              </>
            )}
          </div>
        </>
      }

      {mode === "edit" && editInstance?.created_by && (
        <p className={styles.metadataFooter}>
          {t("rework.teams.formAgent.createdBy", {
            user: userDisplayName(editInstance.created_by, undefined),
          })}
          {editInstance.created_at && ` · ${formatRelativeDate(editInstance.created_at)}`}
          {editInstance.updated_by && (
            <>
              {" — "}
              {t("rework.teams.formAgent.updatedBy", {
                user: userDisplayName(editInstance.updated_by, undefined),
              })}
              {editInstance.updated_at && ` · ${formatRelativeDate(editInstance.updated_at)}`}
            </>
          )}
        </p>
      )}
    </div>
  );
}
