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

import Switch from "@shared/atoms/Switch/Switch.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import { setCapabilityBaseUrls } from "../../../../../common/capabilityRoutingSlice.ts";
import type {
  AgentTemplateSummary,
  ManagedAgentFieldSpec,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useUsersByIdsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { TuningFieldRenderer } from "./TuningFieldRenderer.tsx";
import { CapabilityCard } from "./CapabilityCard/CapabilityCard.tsx";
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
  /** REASON-01 level 3 — offers the composer's reasoning toggle to users. */
  reasoningEnabled: boolean;
  /** REASON-01 Amendment B — that toggle starts ON in every new conversation. */
  reasoningDefaultOn: boolean;
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
  onDisplayNameChange: (v: string) => void;
  onRoleChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onUsageStatementChange: (v: string) => void;
  onReasoningEnabledChange: (v: boolean) => void;
  onReasoningDefaultOnChange: (v: boolean) => void;
  onTuningChange: (key: string, value: unknown) => void;
  onCapabilitySelectionChange: (ids: string[]) => void;
  onCapabilityConfigChange: (capabilityId: string, key: string, value: unknown) => void;
  onCapabilityAssetFileChange: (capabilityId: string, slotKey: string, file: File | null) => void;
  onCapabilityBlockingErrorChange: (capabilityId: string, message: string | null) => void;
};

export function AgentFormBody({
  mode,
  templates,
  templateId,
  displayName,
  role,
  description,
  usageStatement,
  reasoningEnabled,
  reasoningDefaultOn,
  tuningFieldValues,
  selectedCapabilityIds,
  capabilityConfigValues,
  capabilityAssetFiles,
  isSubmitting,
  submitAttempted,
  activeSection,
  onSectionChange,
  errorSections,
  editInstance,
  teamId,
  onDisplayNameChange,
  onRoleChange,
  onDescriptionChange,
  onUsageStatementChange,
  onReasoningEnabledChange,
  onReasoningDefaultOnChange,
  onTuningChange,
  onCapabilitySelectionChange,
  onCapabilityConfigChange,
  onCapabilityAssetFileChange,
  onCapabilityBlockingErrorChange,
}: AgentFormBodyProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();

  // Resolve audit uids (created_by / updated_by) to display names (#1952).
  const auditUids = Array.from(
    new Set([editInstance?.created_by, editInstance?.updated_by].filter((uid): uid is string => Boolean(uid))),
  );
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });
  const auditUserById = new Map(auditUsers.map((summary) => [summary.id, summary]));

  const selectedTemplate = templates.find((tpl) => tpl.template_id === templateId);
  const templateMissing = mode === "edit" && !selectedTemplate;
  const capabilities = selectedTemplate?.available_capabilities ?? [];

  // Pre-save capability routing (RFC §9.1): custom config widgets may call
  // their capability's own pod routes (e.g. ppt_filler's stateless /analyze,
  // #1903) BEFORE any session exists, so the per-capability base URLs are
  // populated here straight from the template catalog — the template-bound
  // counterpart of the prep-time population in `useChatSse`.
  useEffect(() => {
    if (capabilities.length === 0) return;
    dispatch(setCapabilityBaseUrls(Object.fromEntries(capabilities.map((entry) => [entry.id, entry.route_base_url]))));
  }, [dispatch, capabilities]);

  // #1975 (RFC §3.9): a platform-suspended instance renders its broken
  // capability in an error state with plain-language text and the two fix paths
  // (untick/reset the capability and re-save, or contact a platform admin). A
  // successful save re-validates every active slice and clears the suspension —
  // there is no second clearing mechanism. The offending capability id is only
  // derivable for the availability reasons (a selected id the template no
  // longer advertises, including MCP capabilities, which are FGA/team-gated
  // like every other capability); `capability_config_invalid` names no id (the
  // pod's 422 wording is not carried on the summary), so its message is generic.
  const suspensionReason = mode === "edit" ? editInstance?.suspension_reason : undefined;
  const availableCapabilityIds = new Set(capabilities.map((c) => c.id));
  const missingCapabilityIds =
    suspensionReason && suspensionReason !== "capability_config_invalid"
      ? (editInstance?.selected_capability_ids ?? []).filter((id) => !availableCapabilityIds.has(id))
      : [];
  const suspensionMessage = (() => {
    if (!suspensionReason) return undefined;
    const capabilityList = missingCapabilityIds.join(", ") || "—";
    if (suspensionReason === "capability_config_invalid") {
      return t("rework.teams.formAgent.suspended.configInvalid");
    }
    if (suspensionReason === "capability_access_revoked") {
      return t("rework.teams.formAgent.suspended.accessRevoked", { capabilities: capabilityList });
    }
    return t("rework.teams.formAgent.suspended.unavailable", { capabilities: capabilityList });
  })();

  const visibleFields = (selectedTemplate?.default_tuning_fields ?? []).filter((f) => !f.ui?.hide);
  const promptFields = visibleFields.filter((f) => routeField(f) === "prompts");
  const generalFields = visibleFields.filter((f) => routeField(f) === "general");

  const visibleSections = SECTION_ORDER.filter((s) => {
    if (s === "tools") return capabilities.length > 0;
    if (s === "prompts") return promptFields.length > 0;
    return true; // general and commitments always have content
  });

  const effectiveSection = visibleSections.includes(activeSection) ? activeSection : (visibleSections[0] ?? "general");
  const activeSectionIndex = Math.max(0, visibleSections.indexOf(effectiveSection));

  const nameError = submitAttempted && !displayName.trim() ? t("rework.teams.formAgent.fields.name.label") : undefined;
  const usageStatementError =
    submitAttempted && !usageStatement.trim() ? t("rework.teams.formAgent.fields.usageStatement.label") : undefined;

  // Effective value (current input or declared default) of every tuning field,
  // across sections — drives `ui.visible_when` even when the gating field lives
  // in another section.
  const effectiveTuningValues = Object.fromEntries(
    (selectedTemplate?.default_tuning_fields ?? []).map((f) => [f.key, tuningFieldValues[f.key] ?? f.default]),
  );

  const renderFieldList = (fields: ManagedAgentFieldSpec[]) =>
    fields.map((field) => (
      <TuningFieldRenderer
        key={field.key}
        field={field}
        value={tuningFieldValues[field.key]}
        onChange={onTuningChange}
        disabled={isSubmitting}
        teamId={teamId}
        allValues={effectiveTuningValues}
        error={
          submitAttempted && field.required && !tuningFieldValues[field.key] ? `${field.title} is required` : undefined
        }
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

      {suspensionMessage && (
        <div className={styles.suspensionBanner} role="alert">
          <strong>{t("rework.teams.formAgent.suspended.title")}</strong> {suspensionMessage}
        </div>
      )}

      {!templateMissing && (
        <>
          {errorSections.size > 0 && (
            <div className={styles.validationBanner} role="alert">
              {t("rework.teams.formAgent.validation.requiredFields")}
            </div>
          )}

          <div className={styles.tabStrip}>
            <ButtonGroup
              key={visibleSections.join(",")}
              size="medium"
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

          <div className={styles.sectionContent}>
            {effectiveSection === "general" && (
              <>
                <TextInput
                  label={t("rework.teams.formAgent.fields.name.label")}
                  value={displayName}
                  onChange={(e) => onDisplayNameChange(e.target.value)}
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
                <TextArea
                  label={t("rework.teams.formAgent.fields.description.label")}
                  value={description}
                  onChange={(e) => onDescriptionChange(e.target.value)}
                  rows={3}
                  maxLength={500}
                  disabled={isSubmitting}
                />
                {/*
                  REASON-01 level 3. Deliberately HERE and not in the Tools tab:
                  reasoning is a property of how this agent's model is called,
                  not a tool it can use, so asking an author to enable it among
                  the tools would put the decision in the wrong mental model.
                */}
                <div className={styles.switchRow}>
                  <Switch
                    checked={reasoningEnabled}
                    disabled={isSubmitting}
                    onChange={() => onReasoningEnabledChange(!reasoningEnabled)}
                    aria-label={t("rework.teams.formAgent.fields.reasoning.label")}
                  />
                  <div className={styles.switchText}>
                    <span className={styles.switchLabel}>{t("rework.teams.formAgent.fields.reasoning.label")}</span>
                    <span className={styles.switchHint}>{t("rework.teams.formAgent.fields.reasoning.hint")}</span>
                  </div>
                </div>
                {/*
                  REASON-01 Amendment B — where the composer's switch STARTS in a
                  new conversation. Rendered only while the offer above is on:
                  a preselection for a toggle nobody is shown is unanswerable,
                  and hiding it is what makes the nesting read as "and then".
                  The stored value survives hiding, so withdrawing the offer and
                  restoring it later does not silently lose this choice.
                */}
                {reasoningEnabled && (
                  <div className={`${styles.switchRow} ${styles.switchRowNested}`}>
                    <Switch
                      checked={reasoningDefaultOn}
                      disabled={isSubmitting}
                      onChange={() => onReasoningDefaultOnChange(!reasoningDefaultOn)}
                      aria-label={t("rework.teams.formAgent.fields.reasoningDefaultOn.label")}
                    />
                    <div className={styles.switchText}>
                      <span className={styles.switchLabel}>
                        {t("rework.teams.formAgent.fields.reasoningDefaultOn.label")}
                      </span>
                      <span className={styles.switchHint}>
                        {t("rework.teams.formAgent.fields.reasoningDefaultOn.hint")}
                      </span>
                    </div>
                  </div>
                )}
                {renderFieldList(generalFields)}
              </>
            )}
            {effectiveSection === "prompts" && renderFieldList(promptFields)}
            {effectiveSection === "tools" && capabilities.length > 0 && (
              <ul className={styles.toolsList}>
                {capabilities.map((capability) => {
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
                      capability={capability}
                      teamId={teamId}
                      checked={checked}
                      disabled={isSubmitting}
                      configValues={capabilityConfigValues[capability.id] ?? {}}
                      assetFiles={capabilityAssetFiles[capability.id] ?? {}}
                      onToggle={toggle}
                      onConfigChange={(key, val) => onCapabilityConfigChange(capability.id, key, val)}
                      onAssetFileChange={(slotKey, file) => onCapabilityAssetFileChange(capability.id, slotKey, file)}
                      onBlockingErrorChange={(message) => onCapabilityBlockingErrorChange(capability.id, message)}
                    />
                  );
                })}
              </ul>
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
      )}

      {mode === "edit" && editInstance?.created_by && (
        <p className={styles.metadataFooter}>
          {t("rework.teams.formAgent.createdBy", {
            user: userDisplayName(editInstance.created_by, auditUserById.get(editInstance.created_by)),
          })}
          {editInstance.created_at && ` · ${formatRelativeDate(editInstance.created_at)}`}
          {editInstance.updated_by && (
            <>
              {" — "}
              {t("rework.teams.formAgent.updatedBy", {
                user: userDisplayName(editInstance.updated_by, auditUserById.get(editInstance.updated_by)),
              })}
              {editInstance.updated_at && ` · ${formatRelativeDate(editInstance.updated_at)}`}
            </>
          )}
        </p>
      )}
    </div>
  );
}
