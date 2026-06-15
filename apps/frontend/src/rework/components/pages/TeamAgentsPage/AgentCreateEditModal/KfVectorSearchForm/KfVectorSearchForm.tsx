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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { SearchPolicySelect } from "@shared/molecules/SearchPolicySelect/SearchPolicySelect";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";
import {
  SearchPolicyName,
  TagType,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "src/slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryScopePicker } from "../DocumentLibraryScopePicker/DocumentLibraryScopePicker";
import { SwitchRow } from "../SwitchRow/SwitchRow.tsx";
import styles from "./KfVectorSearchForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange, teamId }: ToolParamsProps<KfVectorSearchParams>) {
  const { t } = useTranslation();

  const { data: allLibs = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document" as TagType,
    ...(teamId ? { ownerFilter: "team", teamId } : {}),
  });

  const [bindingEnabled, setBindingEnabled] = useState((params.document_library_tags_ids ?? []).length > 0);

  const handleBindingToggle = (checked: boolean) => {
    setBindingEnabled(checked);
    if (!checked) {
      onParamsChange({ ...params, document_library_tags_ids: [], libraries_selection: false });
    }
  };

  const handleLibraryToggle = (id: string, selected: boolean) => {
    const current = params.document_library_tags_ids ?? [];
    const next = selected ? [...current, id] : current.filter((x) => x !== id);
    onParamsChange({ ...params, document_library_tags_ids: next });
  };

  const handleTopKChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw === "") {
      onParamsChange({ ...params, top_k: null });
    } else {
      const val = parseInt(raw, 10);
      if (!isNaN(val) && val >= 1 && val <= 50) {
        onParamsChange({ ...params, top_k: val });
      }
    }
  };

  return (
    <div className={styles.mainFormCard}>
      <SwitchRow
        label={t("agentTuning.fields.library_binding.title")}
        description={t("agentTuning.fields.library_binding.description")}
        checked={bindingEnabled}
        onChange={handleBindingToggle}
      />

      {bindingEnabled && (
        <div className={styles.libraryList}>
          {allLibs.map((lib) => {
            const selected = (params.document_library_tags_ids ?? []).includes(lib.id);
            return (
              <label key={lib.id} className={styles.libraryRow}>
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={(e) => handleLibraryToggle(lib.id, e.target.checked)}
                  className={styles.libraryCheckbox}
                />
                <div className={styles.libraryInfo}>
                  <span className={styles.libraryName}>{lib.name}</span>
                  {lib.description && <span className={styles.fieldDescription}>{lib.description}</span>}
                </div>
              </label>
            );
          })}
          {allLibs.length === 0 && (
            <span className={styles.fieldDescription}>{t("agentTuning.fields.library_binding.noLibraries")}</span>
          )}
        </div>
      )}

      {!bindingEnabled && (
        <SwitchRow
          label={t("agentTuning.fields.chat_options_libraries_selection.title")}
          description={t("agentTuning.fields.chat_options_libraries_selection.description")}
          checked={Boolean(params.libraries_selection)}
          onChange={(checked) => onParamsChange({ ...params, libraries_selection: checked })}
        />
      )}

      {(bindingEnabled || params.libraries_selection) && (
        <div className={styles.scopePickerSection}>
          <div className={styles.fieldLabel}>
            <span>
              {bindingEnabled
                ? t("agentTuning.fields.library_binding.title")
                : t("agentTuning.fields.chat_options_libraries_selection.title")}
            </span>
            <span className={styles.fieldDescription}>{t("agentTuning.fields.library_scope_picker.description")}</span>
          </div>
          <DocumentLibraryScopePicker
            teamId={teamId}
            selectedTagIds={params.document_library_tags_ids ?? []}
            onChange={(tagIds) => onParamsChange({ ...params, document_library_tags_ids: tagIds })}
          />
        </div>
      )}

      <SwitchRow
        label={t("agentTuning.fields.chat_options_attach_files.title")}
        description={t("agentTuning.fields.chat_options_attach_files.description")}
        checked={Boolean(params.attach_files)}
        onChange={(checked) => onParamsChange({ ...params, attach_files: checked })}
      />
      <SwitchRow
        label={t("agentTuning.fields.chat_options_search_policy_selection.title")}
        description={t("agentTuning.fields.chat_options_search_policy_selection.description")}
        checked={Boolean(params.search_policy_selection)}
        onChange={(checked) => onParamsChange({ ...params, search_policy_selection: checked })}
      />
      {params.search_policy_selection && (
        <div className={styles.fieldRow}>
          <div className={styles.fieldLabel}>
            <span>{t("agentTuning.fields.chat_options_default_search_policy.title")}</span>
            <span className={styles.fieldDescription}>
              {t("agentTuning.fields.chat_options_default_search_policy.description")}
            </span>
          </div>
          <SearchPolicySelect
            value={(params.search_policy as SearchPolicyName) ?? "hybrid"}
            onChange={(next) => onParamsChange({ ...params, search_policy: next })}
          />
        </div>
      )}
      <div className={styles.fieldRow}>
        <div className={styles.fieldLabel}>
          <span>{t("agentTuning.fields.top_k.title")}</span>
          <span className={styles.fieldDescription}>{t("agentTuning.fields.top_k.description")}</span>
        </div>
        <input
          type="number"
          min={1}
          max={50}
          placeholder="10"
          value={params.top_k ?? ""}
          onChange={handleTopKChange}
          className={styles.topKInput}
        />
      </div>
    </div>
  );
}
