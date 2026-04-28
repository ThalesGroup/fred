import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";
import { SwitchRow } from "../SwitchRow/SwitchRow";
import styles from "./KfVectorSearchForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange }: ToolParamsProps<KfVectorSearchParams>) {
  const { t } = useTranslation();

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
    </div>
  );
}
