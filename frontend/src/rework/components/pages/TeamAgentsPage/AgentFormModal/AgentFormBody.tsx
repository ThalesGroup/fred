import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useTranslation } from "react-i18next";
import type {
  AgentTemplateSummary,
  ManagedAgentFieldSpec,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { TemplateBrowser } from "./TemplateBrowser/TemplateBrowser.tsx";
import { TuningFieldRenderer } from "./TuningFieldRenderer.tsx";
import styles from "./AgentFormBody.module.css";

type AgentFormBodyProps = {
  mode: "create" | "edit";
  templates: AgentTemplateSummary[];
  templateId: string;
  displayName: string;
  description: string;
  tuningFieldValues: Record<string, unknown>;
  isSubmitting: boolean;
  submitAttempted: boolean;
  editInstance?: ManagedAgentInstanceSummary;
  onTemplateSelect: (id: string) => void;
  onDisplayNameChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onTuningChange: (key: string, value: unknown) => void;
};

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

function groupFields(fields: ManagedAgentFieldSpec[]): { group: string | null; fields: ManagedAgentFieldSpec[] }[] {
  const groups: Map<string | null, ManagedAgentFieldSpec[]> = new Map();
  for (const field of fields) {
    if (field.ui?.hide) continue;
    const key = field.ui?.group ?? null;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(field);
  }
  const result: { group: string | null; fields: ManagedAgentFieldSpec[] }[] = [];
  if (groups.has(null)) result.push({ group: null, fields: groups.get(null)! });
  for (const [key, fields] of groups) {
    if (key !== null) result.push({ group: key, fields });
  }
  return result;
}

export function AgentFormBody({
  mode,
  templates,
  templateId,
  displayName,
  description,
  tuningFieldValues,
  isSubmitting,
  submitAttempted,
  editInstance,
  onTemplateSelect,
  onDisplayNameChange,
  onDescriptionChange,
  onTuningChange,
}: AgentFormBodyProps) {
  const { t } = useTranslation();

  const selectedTemplate = templates.find((tpl) => tpl.template_id === templateId);
  const visibleFields = (selectedTemplate?.default_tuning_fields ?? []).filter((f) => !f.ui?.hide);
  const fieldGroups = groupFields(visibleFields);
  const mcpServers = selectedTemplate?.mcp_servers ?? [];
  const templateMissing = mode === "edit" && !selectedTemplate;

  const nameError = submitAttempted && !displayName.trim() ? t("rework.teams.formAgent.fields.name.label") : undefined;

  return (
    <div className={styles.body}>
      {mode === "create" ? (
        <section className={styles.section}>
          <h3 className={styles.sectionHeader}>{t("rework.teams.formAgent.templateSection")}</h3>
          <TemplateBrowser
            templates={templates}
            selectedId={templateId}
            onSelect={onTemplateSelect}
          />
        </section>
      ) : (
        <div className={styles.contextBar}>
          <span className={styles.contextName}>
            {selectedTemplate?.display_name ?? templateId}
          </span>
          {selectedTemplate?.category && (
            <span className={styles.contextCategory}>{selectedTemplate.category}</span>
          )}
        </div>
      )}

      {templateMissing && (
        <p className={styles.templateUnavailableNotice}>
          {t("rework.teams.formAgent.templateUnavailable")}
        </p>
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

          {fieldGroups.length > 0 && (
            <section className={styles.section}>
              <h3 className={styles.sectionHeader}>{t("rework.teams.formAgent.tunableFields")}</h3>
              {fieldGroups.map(({ group, fields }) => (
                <div key={group ?? "__ungrouped"} className={styles.fieldGroup}>
                  {group && <p className={styles.groupLabel}>{group}</p>}
                  {fields.map((field) => (
                    <TuningFieldRenderer
                      key={field.key}
                      field={field}
                      value={tuningFieldValues[field.key]}
                      onChange={onTuningChange}
                      disabled={isSubmitting}
                      error={
                        submitAttempted && field.required && !tuningFieldValues[field.key]
                          ? `${field.title} is required`
                          : undefined
                      }
                    />
                  ))}
                </div>
              ))}
            </section>
          )}

          {mcpServers.length > 0 && (
            <section className={styles.section}>
              <h3 className={styles.sectionHeader}>{t("rework.teams.formAgent.mcpTools")}</h3>
              <ul className={styles.mcpList}>
                {mcpServers.map((server) => (
                  <li key={server.id} className={styles.mcpItem}>
                    <span className={styles.mcpName}>
                      {t(server.display_name || server.id, { defaultValue: server.id })}
                    </span>
                    {server.require_tools && server.require_tools.length > 0 && (
                      <span className={styles.mcpTools}>{server.require_tools.join(", ")}</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
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
