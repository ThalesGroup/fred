import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { SwitchRow } from "../SwitchRow/SwitchRow";
import styles from "./DocumentCapacityForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange }: ToolParamsProps) {
  const { t } = useTranslation();

  const attachFiles = Boolean(params["chat_options.attach_files"]);
  const librariesSelection = Boolean(params["chat_options.libraries_selection"]);

  return (
    <div className={styles["mainFormCard"]}>
      <SwitchRow
        label={t("agentTuning.fields.chat_options_attach_files.title")}
        description={t("agentTuning.fields.chat_options_attach_files.description")}
        checked={attachFiles}
        onChange={(checked) => onParamsChange({ ...params, "chat_options.attach_files": checked })}
      />
      <SwitchRow
        label={t("agentTuning.fields.chat_options_libraries_selection.title")}
        description={t("agentTuning.fields.chat_options_libraries_selection.description")}
        checked={librariesSelection}
        onChange={(checked) => onParamsChange({ ...params, "chat_options.libraries_selection": checked })}
      />
    </div>
  );
}
