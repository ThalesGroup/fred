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
import { PromptPicker } from "@shared/molecules/PromptPicker/PromptPicker.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import TagInput from "@shared/molecules/TagInput/TagInput.tsx";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ManagedAgentFieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import {
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
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
};

export function TuningFieldRenderer({ field, value, onChange, disabled, error, teamId }: TuningFieldRendererProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.split("-")[0];
  const fieldDescription = field.description_by_lang?.[lang] ?? field.description;
  const isPromptField = field.type === "prompt";

  // null = auto: picker shown when field is empty, textarea shown when field has value.
  // true = user explicitly opened picker from editing mode.
  // false = user explicitly chose to write from scratch (override auto-picker for empty fields).
  const [pickerExplicit, setPickerExplicit] = useState<boolean | null>(null);

  const { data: contextPrompts = [] } = useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery(
    { teamId: teamId ?? "", lang },
    { skip: !teamId || !isPromptField },
  );

  // Index by id so handlePickPrompt can use embedded text for default prompts
  // without an extra API call (default IDs are synthetic, not real DB rows).
  const contextPromptMap = useMemo(() => new Map(contextPrompts.map((p) => [p.id, p])), [contextPrompts]);

  const [fetchDetail, { isLoading: isLoadingDetail }] =
    useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery();

  const [recordUse] = usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation();

  const handlePickPrompt = async (promptId: string) => {
    const cached = contextPromptMap.get(promptId);
    if (cached?.text) {
      // Default prompt — text is embedded in the summary, no fetch needed.
      onChange(field.key, cached.text);
      setPickerExplicit(null);
    } else {
      if (!teamId) return;
      const result = await fetchDetail({ teamId, promptId });
      if (!result.data) return;
      onChange(field.key, result.data.text);
      setPickerExplicit(null);
    }
    // Fire-and-forget: record usage for both default and custom prompts.
    if (teamId) {
      recordUse({ teamId, promptId }).catch(() => {});
    }
  };

  if (field.ui?.hide) return null;

  const fieldValue = value ?? field.default ?? "";
  const label = `${field.title}${field.required ? " *" : ""}`;

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
          label={field.title}
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
          <div className={styles.promptPickerHeader}>
            <span className={styles.promptPickerLabel}>{label}</span>
            <Button
              color="on-surface"
              variant="text"
              size="small"
              icon={{ category: "outlined", type: "edit" }}
              onClick={() => setPickerExplicit(false)}
              disabled={disabled}
            >
              {t("rework.teams.formAgent.promptField.writeFromScratch")}
            </Button>
          </div>
          <PromptPicker prompts={contextPrompts} disabled={disabled || isLoadingDetail} onSelect={handlePickPrompt} />
          {error && <p className={styles.error}>{error}</p>}
        </div>
      );
    }

    return (
      <div className={styles.promptFieldWrapper}>
        {hasLibrary && (
          <div className={styles.promptEditingHeader}>
            <Button
              color="on-surface"
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
