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

// The Simple Team documents pack reuses the Advanced document-access setting
// for library scoping.

import { DocumentLibraryScopePicker } from "@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker.tsx";
import { DOCUMENT_SELECTION_SUPPORTED } from "@shared/molecules/DocumentLibraryScopePicker/documentLibrarySelection";
import { useTranslation } from "react-i18next";
import { SwitchRow } from "../../AgentCreateEditModal/SwitchRow/SwitchRow.tsx";
import styles from "./DocumentAccessPackOptions.module.css";

interface DocumentAccessPackOptionsProps {
  /** Current document_access config values. */
  configValues: Record<string, unknown>;
  /** Patch one document_access config value (writes back into the pack selection). */
  onConfigChange: (key: string, value: unknown) => void;
  teamId?: string;
  disabled?: boolean;
}

export function DocumentAccessPackOptions({
  configValues,
  onConfigChange,
  teamId,
  disabled = false,
}: DocumentAccessPackOptionsProps) {
  const { t } = useTranslation();
  const bindLibraries = Boolean(configValues.bind_libraries) || Array.isArray(configValues.document_uids);
  const selectedFolderIds =
    configValues.bind_libraries && Array.isArray(configValues.library_tag_ids)
      ? (configValues.library_tag_ids as string[])
      : [];

  const selectedDocumentIds = Array.isArray(configValues.document_uids) ? (configValues.document_uids as string[]) : [];

  return (
    <div className={styles.root}>
      <SwitchRow
        size="small"
        label={t("capability.document_access.fields.bind_libraries.title")}
        description={t("capability.document_access.fields.bind_libraries.description")}
        checked={bindLibraries}
        disabled={disabled || !DOCUMENT_SELECTION_SUPPORTED}
        onChange={(checked) => onConfigChange("bind_libraries", checked)}
      />
      {!DOCUMENT_SELECTION_SUPPORTED && <p>{t("rework.weaverAgents.documentSelectionUnavailable")}</p>}
      {bindLibraries && (
        <div className={styles.treeCard}>
          <DocumentLibraryScopePicker
            spaceId={teamId ?? ""}
            value={{ folderIds: selectedFolderIds, documentIds: selectedDocumentIds }}
            onChange={(selection) => {
              onConfigChange("bind_libraries", true);
              onConfigChange("library_tag_ids", selection.folderIds);
              onConfigChange("document_uids", selection.documentIds);
            }}
            showDocuments
            disabled={disabled || !DOCUMENT_SELECTION_SUPPORTED}
          />
        </div>
      )}
    </div>
  );
}
