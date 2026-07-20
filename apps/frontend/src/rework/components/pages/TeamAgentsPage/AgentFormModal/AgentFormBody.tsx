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
import { IconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import type {
  AgentTemplateSummary,
  ManagedAgentFieldSpec,
  ManagedAgentInstanceSummary,
  UserSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useUsersByIdsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import { TuningFieldRenderer } from "./TuningFieldRenderer.tsx";
import { CapabilityCard } from "./CapabilityCard/CapabilityCard.tsx";
import styles from "./AgentFormBody.module.css";

export type SectionKey = "prompts" | "settings" | "chat" | "tools";

const SECTION_ORDER: SectionKey[] = ["prompts", "settings", "chat", "tools"];

const SECTION_LABEL_KEYS: Record<SectionKey, string> = {
  prompts: "rework.teams.formAgent.sections.prompts",
  settings: "rework.teams.formAgent.sections.settings",
  chat: "rework.teams.formAgent.sections.chat",
  tools: "rework.teams.formAgent.sections.tools",
};

const SECTION_ICONS: Record<SectionKey, { category: "outlined"; type: IconType }> = {
  prompts: { category: "outlined", type: "edit_note" },
  settings: { category: "outlined", type: "tune" },
  chat: { category: "outlined", type: "forum" },
  tools: { category: "outlined", type: "build" },
};

function routeField(field: ManagedAgentFieldSpec): "prompts" | "settings" | "chat" {
  const g = (field.ui?.group ?? "").toLowerCase().trim();
  if (g === "prompts") return "prompts";
  if (g === "chat") return "chat";
  return "settings";
}

/** Human display for a resolved user: full name, else username, else the raw uid (#1952). */
function userDisplayName(uid: string, summary: UserSummary | undefined): string {
  if (!summary) return uid;
  const fullName = [summary.first_name, summary.last_name].filter(Boolean).join(" ");
  return fullName || summary.username || uid;
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
  description: string;
  tuningFieldValues: Record<string, unknown>;
  /** Explicit list of active capability ids ([] = none active). */
  selectedCapabilityIds: string[];
  /** Per-capability config values: outer key = capability id, inner key = config_fields[].key. */
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  isSubmitting: boolean;
  submitAttempted: boolean;
  activeSection: SectionKey;
  onSectionChange: (s: SectionKey) => void;
  errorSections: Set<SectionKey>;
  editInstance?: ManagedAgentInstanceSummary;
  teamId?: string;
  onDisplayNameChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onTuningChange: (key: string, value: unknown) => void;
  onCapabilitySelectionChange: (ids: string[]) => void;
  onCapabilityConfigChange: (capabilityId: string, key: string, value: unknown) => void;
};

export function AgentFormBody({
  mode,
  templates,
  templateId,
  displayName,
  description,
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
  onDisplayNameChange,
  onDescriptionChange,
  onTuningChange,
  onCapabilitySelectionChange,
  onCapabilityConfigChange,
}: AgentFormBodyProps) {
  const { t } = useTranslation();

  // Resolve audit uids (created_by / updated_by) to display names (#1952).
  const auditUids = Array.from(
    new Set([editInstance?.created_by, editInstance?.updated_by].filter((uid): uid is string => Boolean(uid))),
  );
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });
  const auditUserById = new Map(auditUsers.map((summary) => [summary.id, summary]));

  const selectedTemplate = templates.find((tpl) => tpl.template_id === templateId);
  const templateMissing = mode === "edit" && !selectedTemplate;
  const capabilities = selectedTemplate?.available_capabilities ?? [];

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
  const settingsFields = visibleFields.filter((f) => routeField(f) === "settings");
  const chatFields = visibleFields.filter((f) => routeField(f) === "chat");

  const fieldsBySection: Record<"prompts" | "settings" | "chat", ManagedAgentFieldSpec[]> = {
    prompts: promptFields,
    settings: settingsFields,
    chat: chatFields,
  };

  const visibleSections = SECTION_ORDER.filter((s) => {
    if (s === "tools") return capabilities.length > 0;
    return fieldsBySection[s].length > 0;
  });

  const effectiveSection = visibleSections.includes(activeSection) ? activeSection : (visibleSections[0] ?? "settings");
  const activeSectionIndex = Math.max(0, visibleSections.indexOf(effectiveSection));

  const nameError = submitAttempted && !displayName.trim() ? t("rework.teams.formAgent.fields.name.label") : undefined;

  const renderFieldList = (fields: ManagedAgentFieldSpec[]) =>
    fields.map((field) => (
      <TuningFieldRenderer
        key={field.key}
        field={field}
        value={tuningFieldValues[field.key]}
        onChange={onTuningChange}
        disabled={isSubmitting}
        teamId={teamId}
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
      {selectedTemplate ? (
        <div className={styles.contextBar}>
          <span className={styles.contextName}>{selectedTemplate.display_name}</span>
          {selectedTemplate.category && <span className={styles.contextCategory}>{selectedTemplate.category}</span>}
        </div>
      ) : templateMissing ? (
        <p className={styles.templateUnavailableNotice}>{t("rework.teams.formAgent.templateUnavailable")}</p>
      ) : null}

      {suspensionMessage && (
        <div className={styles.suspensionBanner} role="alert">
          <strong>{t("rework.teams.formAgent.suspended.title")}</strong> {suspensionMessage}
        </div>
      )}

      {!templateMissing && (
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
          <TextArea
            label={t("rework.teams.formAgent.fields.description.label")}
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            rows={3}
            maxLength={500}
            disabled={isSubmitting}
          />

          {visibleSections.length > 0 && (
            <>
              <div className={styles.tabStrip}>
                <ButtonGroup
                  key={visibleSections.join(",")}
                  size="small"
                  color="secondary"
                  variant="tabs"
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

              {errorSections.size > 0 && (
                <div className={styles.validationBanner} role="alert">
                  {t("rework.teams.formAgent.validation.requiredFields")}
                </div>
              )}

              <div className={styles.sectionContent}>
                {effectiveSection === "prompts" && renderFieldList(promptFields)}
                {effectiveSection === "settings" && renderFieldList(settingsFields)}
                {effectiveSection === "chat" && renderFieldList(chatFields)}
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
                          onToggle={toggle}
                          onConfigChange={(key, val) => onCapabilityConfigChange(capability.id, key, val)}
                        />
                      );
                    })}
                  </ul>
                )}
              </div>
            </>
          )}
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
