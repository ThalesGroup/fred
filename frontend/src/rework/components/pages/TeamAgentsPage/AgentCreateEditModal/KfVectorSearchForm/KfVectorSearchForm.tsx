import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ToolParamsProps } from "src/components/agentHub/toolParams/toolParamsRegistry";
import { ChatDocumentLibrariesSelectionCard } from "src/features/libraries/components/ChatDocumentLibrariesSelectionCard";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "src/slices/knowledgeFlow/knowledgeFlowOpenApi";
import { SwitchRow } from "../SwitchRow/SwitchRow";
import styles from "./KfVectorSearchForm.module.css";

export function KfVectorSearchForm({ params, onParamsChange, teamId }: ToolParamsProps<KfVectorSearchParams>) {
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();

  const { data: allLibraries = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document",
    ownerFilter: teamId ? "team" : "personal",
    teamId: teamId,
  });

  const allLibraryIds = useMemo(() => allLibraries.map((lib) => lib.id), [allLibraries]);

  // When the tool is first enabled (document_library_tags_ids is null/undefined),
  // pre-select all available libraries so the user sees explicit access rather than nothing.
  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current) return;
    if (params.document_library_tags_ids != null) {
      // Already set (editing an existing agent) — do not override.
      initializedRef.current = true;
      return;
    }
    if (allLibraryIds.length > 0) {
      initializedRef.current = true;
      onParamsChange({ ...params, document_library_tags_ids: allLibraryIds });
    }
  }, [allLibraryIds, params, onParamsChange]);

  return (
    <div className={styles.mainFormCard}>
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
      <div className={styles.directorySelectionCard}>
        <div className={styles.directorySelectionLabelSection}>
          <span className={styles.directorySelectionTitle}>
            {t("agentTuning.fields.chat_options_libraries_selection.library_selection")}
          </span>
          <span className={styles.directorySelectionDescription}>
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
