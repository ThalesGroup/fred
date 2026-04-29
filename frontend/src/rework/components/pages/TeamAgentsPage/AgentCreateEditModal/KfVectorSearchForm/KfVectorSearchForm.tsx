import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";
import { SwitchRow } from "../SwitchRow/SwitchRow";
import styles from "./KfVectorSearchForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange }: ToolParamsProps<KfVectorSearchParams>) {
  const { t } = useTranslation();

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
        label={t("agentTuning.fields.chat_options_libraries_selection.title")}
        description={t("agentTuning.fields.chat_options_libraries_selection.description")}
        checked={Boolean(params.libraries_selection)}
        onChange={(checked) => onParamsChange({ ...params, libraries_selection: checked })}
      />
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
