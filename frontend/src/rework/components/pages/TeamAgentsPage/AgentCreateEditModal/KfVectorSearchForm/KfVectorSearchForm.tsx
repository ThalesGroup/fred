import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";
import { TagType, useListAllTagsKnowledgeFlowV1TagsGetQuery } from "src/slices/knowledgeFlow/knowledgeFlowOpenApi";
import { SwitchRow } from "../SwitchRow/SwitchRow";
import styles from "./KfVectorSearchForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange }: ToolParamsProps<KfVectorSearchParams>) {
  const { t } = useTranslation();

  const { data: allLibs = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" as TagType });

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
      {/* Hard library binding */}
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
                  {lib.description && (
                    <span className={styles.fieldDescription}>{lib.description}</span>
                  )}
                </div>
              </label>
            );
          })}
          {allLibs.length === 0 && (
            <span className={styles.fieldDescription}>{t("agentTuning.fields.library_binding.noLibraries")}</span>
          )}
        </div>
      )}

      {/* Runtime options — library picker hidden when hard binding is active */}
      {!bindingEnabled && (
        <SwitchRow
          label={t("agentTuning.fields.chat_options_libraries_selection.title")}
          description={t("agentTuning.fields.chat_options_libraries_selection.description")}
          checked={Boolean(params.libraries_selection)}
          onChange={(checked) => onParamsChange({ ...params, libraries_selection: checked })}
        />
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
