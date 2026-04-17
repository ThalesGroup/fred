import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { ChatDocumentLibrariesSelectionCard } from "src/features/libraries/components/ChatDocumentLibrariesSelectionCard";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";
import { SwitchRow } from "../SwitchRow/SwitchRow";
import styles from "./KfVectorSearchForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange, teamId }: ToolParamsProps<KfVectorSearchParams>) {
  const { t } = useTranslation();

  return (
    <div className={styles["mainFormCard"]}>
      <SwitchRow
        label={t("agentTuning.fields.chat_options_attach_files.title")}
        description={t("agentTuning.fields.chat_options_attach_files.description")}
        checked={Boolean(params.attach_files)}
        onChange={(checked) => onParamsChange({ ...params, attach_files: checked })}
      />
      <SwitchRow
        label={t("agentTuning.fields.chat_options_libraries_selection.title")}
        description={t("agentTuning.fields.chat_options_libraries_selection.description")}
        checked={Boolean(params.libraries_selection)}
        onChange={(checked) => onParamsChange({ ...params, libraries_selection: checked })}
      />
      <div className={styles["directorySelecttionCard"]}>
        <span className={styles["directorySelectionTitle"]}>
          {t("agentTuning.fields.chat_options_libraries_selection.library_selection")}
        </span>
        <ChatDocumentLibrariesSelectionCard
          libraryType={"document"}
          selectedLibrariesIds={params.document_library_tags_ids ?? []}
          setSelectedLibrariesIds={(ids) => onParamsChange({ ...params, document_library_tags_ids: ids })}
          teamId={teamId}
        />
      </div>
    </div>
  );
}
