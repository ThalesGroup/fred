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
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  AgentTemplateSummary,
  ManagedAgentFieldSpec,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { TuningFieldRenderer } from "./TuningFieldRenderer.tsx";
import { McpServerCard } from "./McpServerCard/McpServerCard.tsx";
import styles from "./AgentFormBody.module.css";

type SectionKey = "prompts" | "settings" | "chat" | "tools";

const SECTION_ORDER: SectionKey[] = ["prompts", "settings", "chat", "tools"];

const SECTION_LABELS: Record<SectionKey, string> = {
  prompts: "Prompts",
  settings: "Settings",
  chat: "Chat",
  tools: "Tools",
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
  selectedMcpServerIds: string[] | null;
  isSubmitting: boolean;
  submitAttempted: boolean;
  editInstance?: ManagedAgentInstanceSummary;
  onDisplayNameChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onTuningChange: (key: string, value: unknown) => void;
  onMcpSelectionChange: (ids: string[]) => void;
};

export function AgentFormBody({
  mode,
  templates,
  templateId,
  displayName,
  description,
  tuningFieldValues,
  selectedMcpServerIds,
  isSubmitting,
  submitAttempted,
  editInstance,
  onDisplayNameChange,
  onDescriptionChange,
  onTuningChange,
  onMcpSelectionChange,
}: AgentFormBodyProps) {
  const { t } = useTranslation();
  const [activeSection, setActiveSection] = useState<SectionKey>("settings");

  const selectedTemplate = templates.find((tpl) => tpl.template_id === templateId);
  const templateMissing = mode === "edit" && !selectedTemplate;
  const mcpServers = selectedTemplate?.mcp_servers ?? [];

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
    if (s === "tools") return mcpServers.length > 0;
    return fieldsBySection[s].length > 0;
  });

  const effectiveSection = visibleSections.includes(activeSection) ? activeSection : (visibleSections[0] ?? "settings");

  const defaultSectionIndex = Math.max(0, visibleSections.indexOf(effectiveSection));

  const nameError = submitAttempted && !displayName.trim() ? t("rework.teams.formAgent.fields.name.label") : undefined;

  const renderFieldList = (fields: ManagedAgentFieldSpec[]) =>
    fields.map((field) => (
      <TuningFieldRenderer
        key={field.key}
        field={field}
        value={tuningFieldValues[field.key]}
        onChange={onTuningChange}
        disabled={isSubmitting}
        error={
          submitAttempted && field.required && !tuningFieldValues[field.key] ? `${field.title} is required` : undefined
        }
      />
    ));

  return (
    <div className={styles.body}>
      {selectedTemplate ? (
        <div className={styles.contextBar}>
          <span className={styles.contextName}>{selectedTemplate.display_name}</span>
          {selectedTemplate.category && <span className={styles.contextCategory}>{selectedTemplate.category}</span>}
        </div>
      ) : templateMissing ? (
        <p className={styles.templateUnavailableNotice}>{t("rework.teams.formAgent.templateUnavailable")}</p>
      ) : null}

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
                  defaultSelectedIndex={defaultSectionIndex}
                  items={visibleSections.map((s) => ({
                    label: SECTION_LABELS[s],
                    icon: SECTION_ICONS[s],
                    onClick: () => setActiveSection(s),
                  }))}
                />
              </div>

              <div className={styles.sectionContent}>
                {effectiveSection === "prompts" && renderFieldList(promptFields)}
                {effectiveSection === "settings" && renderFieldList(settingsFields)}
                {effectiveSection === "chat" && renderFieldList(chatFields)}
                {effectiveSection === "tools" && (
                  <ul className={styles.mcpList}>
                    {mcpServers.map((server) => {
                      const checked = selectedMcpServerIds === null || selectedMcpServerIds.includes(server.id);
                      const toggle = () => {
                        const current = selectedMcpServerIds ?? mcpServers.map((s) => s.id);
                        const next = checked
                          ? current.filter((id) => id !== server.id)
                          : [...current.filter((id) => id !== server.id), server.id];
                        onMcpSelectionChange(next);
                      };
                      return (
                        <McpServerCard
                          key={server.id}
                          server={server}
                          checked={checked}
                          disabled={isSubmitting}
                          tuningFieldValues={tuningFieldValues}
                          onToggle={toggle}
                          onTuningChange={onTuningChange}
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
          {t("rework.teams.formAgent.createdBy", { user: editInstance.created_by })}
          {editInstance.created_at && ` · ${formatRelativeDate(editInstance.created_at)}`}
        </p>
      )}
    </div>
  );
}
