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
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { DocumentLibraryScopePicker } from "@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker.tsx";
import { PromptPicker } from "@shared/molecules/PromptPicker/PromptPicker.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import TagInput from "@shared/molecules/TagInput/TagInput.tsx";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ManagedAgentFieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import {
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery,
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
  usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { SwitchRow } from "../AgentCreateEditModal/SwitchRow/SwitchRow.tsx";
import styles from "./TuningFieldRenderer.module.css";

type TuningFieldRendererProps = {
  field: ManagedAgentFieldSpec;
  value: unknown;
  onChange: (key: string, value: unknown) => void;
  disabled: boolean;
  error?: string;
  teamId?: string;
  /** Effective values (current input or declared default) of every sibling field
   * in the same form — drives the `ui.visible_when` conditional display. */
  allValues?: Record<string, unknown>;
};

export function TuningFieldRenderer({
  field,
  value,
  onChange,
  disabled,
  error,
  teamId,
  allValues,
}: TuningFieldRendererProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.split("-")[0];
  const descriptionKey = field.description_by_lang?.[lang] ?? field.description;
  const fieldDescription = descriptionKey ? t(descriptionKey, { defaultValue: descriptionKey }) : undefined;
  const fieldTitle = t(field.title, { defaultValue: field.title });
  const isPromptField = field.type === "prompt";

  // null = auto: picker shown when field is empty, textarea shown when field has value.
  // true = user explicitly opened picker from editing mode.
  // false = user explicitly chose to write from scratch (override auto-picker for empty fields).
  const [pickerExplicit, setPickerExplicit] = useState<boolean | null>(null);

  const { data: contextPrompts = [] } = useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery(
    { teamId: teamId ?? "" },
    { skip: !teamId || !isPromptField },
  );
  const { data: promptCategories = [] } = useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery(
    { teamId: teamId ?? "" },
    { skip: !teamId || !isPromptField },
  );

  const [fetchDetail, { isLoading: isLoadingDetail }] =
    useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery();

  const [recordUse] = usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation();

  const handlePickPrompt = async (promptId: string) => {
    if (!teamId) return;
    const result = await fetchDetail({ teamId, promptId });
    if (!result.data) return;
    onChange(field.key, result.data.text);
    setPickerExplicit(null);
    // Fire-and-forget usage tracking.
    recordUse({ teamId, promptId }).catch(() => {});
  };

  if (field.ui?.hide) return null;
  // `ui.visible_when`: show only while the referenced sibling's effective
  // value is truthy. Display-only — the hidden field keeps its stored value.
  if (field.ui?.visible_when && !allValues?.[field.ui.visible_when]) return null;

  const fieldValue = value ?? field.default ?? "";
  const label = `${fieldTitle}${field.required ? " *" : ""}`;

  if (field.enum && field.enum.length > 0) {
    return (
      <div className={styles.field}>
        <Select
          size="medium"
          label={label}
          value={String(fieldValue)}
          options={field.enum.map((opt) => ({ value: opt, label: opt, key: opt }))}
          onChange={(v) => onChange(field.key, v)}
          disabled={disabled}
          error={error}
          placeholder={t("rework.teams.formAgent.selectPlaceholder")}
        />
        {fieldDescription && <p className={styles.hint}>{fieldDescription}</p>}
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <div className={styles.field}>
        <SwitchRow
          label={fieldTitle}
          description={fieldDescription ?? ""}
          checked={Boolean(fieldValue)}
          onChange={(checked) => onChange(field.key, checked)}
        />
        {error && <p className={styles.error}>{error}</p>}
      </div>
    );
  }

  const isMultiline =
    field.ui?.multiline || field.ui?.textarea || field.type === "prompt" || field.type === "text-multiline";

  if (isMultiline) {
    const hasLibrary = isPromptField && contextPrompts.length > 0;
    const hasValue = String(fieldValue).trim() !== "";

    // Show the picker grid when: explicitly requested, OR auto mode with empty field.
    const showPicker = hasLibrary && (pickerExplicit === true || (pickerExplicit === null && !hasValue));

    if (showPicker) {
      return (
        <div className={styles.promptPickerMode}>
          <div className={styles.promptPickerContainer}>
            <div className={styles.promptPickerHeader}>
              <span className={styles.promptPickerLabel}>{t("rework.teams.formAgent.promptField.libraryTitle")}</span>
              <Button
                color="on-surface-retreat"
                variant="text"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                onClick={() => setPickerExplicit(false)}
                disabled={disabled}
              >
                {t("rework.teams.formAgent.promptField.closeLibrary")}
              </Button>
            </div>
            <PromptPicker
              prompts={contextPrompts}
              categories={promptCategories}
              disabled={disabled || isLoadingDetail}
              onSelect={handlePickPrompt}
            />
          </div>
          {error && <p className={styles.error}>{error}</p>}
        </div>
      );
    }

    return (
      <div className={styles.promptFieldWrapper}>
        {hasLibrary && (
          <div className={styles.promptEditingHeader}>
            <Button
              color="primary"
              variant="text"
              size="small"
              icon={{ category: "outlined", type: "edit_note" }}
              onClick={() => setPickerExplicit(true)}
              disabled={disabled}
            >
              {t("rework.teams.formAgent.promptField.pickFromLibrary")}
            </Button>
          </div>
        )}
        <TextArea
          label={label}
          value={String(fieldValue)}
          rows={field.ui?.max_lines ?? 4}
          placeholder={field.ui?.placeholder ?? undefined}
          onChange={(e) => onChange(field.key, e.target.value)}
          disabled={disabled || isLoadingDetail}
          error={error}
        />
      </div>
    );
  }

  if (field.type === "array") {
    const tags = Array.isArray(value) ? (value as string[]) : [];

    // `ui.widget` stock form widgets. "document_libraries" renders the
    // library/document tree picker instead of a raw tag-id text input; an
    // unknown widget id falls through to the default TagInput.
    if (field.ui?.widget === "document_libraries") {
      return (
        <div className={styles.field}>
          <span className={styles.label}>{label}</span>
          <DocumentLibraryScopePicker
            teamId={teamId}
            selectedTagIds={tags}
            onChange={(tagIds) => onChange(field.key, tagIds)}
          />
          {fieldDescription && <p className={styles.hint}>{fieldDescription}</p>}
          {error && <p className={styles.error}>{error}</p>}
        </div>
      );
    }

    return (
      <div className={styles.field}>
        <TagInput
          label={label}
          tags={tags}
          onChange={(newTags) => onChange(field.key, newTags)}
          disabled={disabled}
          placeholder={t("rework.teams.formAgent.promptField.tagsPlaceholder")}
          removeTagAriaLabel={(tag) => t("rework.teams.formAgent.promptField.removeTagAria", { tag })}
          error={error}
        />
        {fieldDescription && <p className={styles.hint}>{fieldDescription}</p>}
      </div>
    );
  }

  const inputType =
    field.type === "secret"
      ? "password"
      : field.type === "url"
        ? "url"
        : field.type === "number" || field.type === "integer"
          ? "number"
          : "text";

  return (
    <TextInput
      label={label}
      value={String(fieldValue)}
      type={inputType}
      autoComplete={field.type === "secret" ? "new-password" : undefined}
      min={field.min ?? undefined}
      max={field.max ?? undefined}
      onChange={(e) => onChange(field.key, inputType === "number" ? Number(e.target.value) : e.target.value)}
      disabled={disabled}
      required={field.required}
      error={error}
      explanation={fieldDescription ?? undefined}
    />
  );
}
