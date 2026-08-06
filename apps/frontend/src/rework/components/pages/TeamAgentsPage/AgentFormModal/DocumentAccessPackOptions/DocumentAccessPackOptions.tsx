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

// The "team resources" pack options (Simple capabilities view): a leaner take on
// the Advanced document_access folder-scoping. It reuses the same two config
// keys — `bind_libraries` (the "restrict to specific folders" switch) and
// `library_tag_ids` (the picked folders) — and the SAME labels as the Advanced
// card, but strips the field label and hint around the tree and drops the folder
// picker onto its own tinted card, for a simpler look suited to Simple mode.

import { DocumentLibraryScopePicker } from "@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker.tsx";
import { useTranslation } from "react-i18next";
import { SwitchRow } from "../../AgentCreateEditModal/SwitchRow/SwitchRow.tsx";
import styles from "./DocumentAccessPackOptions.module.css";

interface DocumentAccessPackOptionsProps {
  /** document_access's current config values (`bind_libraries`, `library_tag_ids`). */
  configValues: Record<string, unknown>;
  /** Patch one document_access config value (writes back into the pack selection). */
  onConfigChange: (key: string, value: unknown) => void;
  teamId?: string;
}

export function DocumentAccessPackOptions({ configValues, onConfigChange, teamId }: DocumentAccessPackOptionsProps) {
  const { t } = useTranslation();
  const bindLibraries = Boolean(configValues.bind_libraries);
  const selectedTagIds = Array.isArray(configValues.library_tag_ids) ? (configValues.library_tag_ids as string[]) : [];

  return (
    <div className={styles.root}>
      <SwitchRow
        label={t("capability.document_access.fields.bind_libraries.title")}
        description={t("capability.document_access.fields.bind_libraries.description")}
        checked={bindLibraries}
        onChange={(checked) => onConfigChange("bind_libraries", checked)}
      />
      {bindLibraries && (
        <div className={styles.treeCard}>
          <DocumentLibraryScopePicker
            teamId={teamId}
            selectedTagIds={selectedTagIds}
            onChange={(tagIds) => onConfigChange("library_tag_ids", tagIds)}
          />
        </div>
      )}
    </div>
  );
}
