import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { ChatDocumentLibrariesSelectionCard } from "src/features/libraries/components/ChatDocumentLibrariesSelectionCard";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";
import { SwitchRow } from "../SwitchRow/SwitchRow";
import styles from "./KfVectorSearchForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange, teamId }: ToolParamsProps<KfVectorSearchParams>) {
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();

  return (
    <div className={styles["mainFormCard"]}>
      {/* Allow attaching files */}
      <SwitchRow
        label={t("agentTuning.fields.chat_options_attach_files.title")}
        description={t("agentTuning.fields.chat_options_attach_files.description")}
        checked={Boolean(params.attach_files)}
        onChange={(checked) => onParamsChange({ ...params, attach_files: checked })}
      />

      {/* Allow library selection */}
      <SwitchRow
        label={t("agentTuning.fields.chat_options_libraries_selection.title")}
        description={t("agentTuning.fields.chat_options_libraries_selection.description")}
        checked={Boolean(params.libraries_selection)}
        onChange={(checked) => onParamsChange({ ...params, libraries_selection: checked })}
      />

      {/* Directories selection */}
      <div className={styles["directorySelectionCard"]}>
        <div className={styles["directorySelectionLabelSection"]}>
          <span className={styles["directorySelectionTitle"]}>
            {t("agentTuning.fields.chat_options_libraries_selection.library_selection")}
          </span>
          <span className={styles["directorySelectionDescription"]}>
            {t("agentTuning.fields.chat_options_libraries_selection.library_selection_description", {
              agentsNicknameSingular,
            })}
          </span>
        </div>

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
