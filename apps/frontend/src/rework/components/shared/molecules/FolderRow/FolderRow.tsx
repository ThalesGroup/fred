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

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton.tsx";
import styles from "./FolderRow.module.css";

/** Counts of the folder's documents that are in a noteworthy state. */
interface FolderAggregate {
  processing: number;
  failed: number;
}

interface FolderRowProps {
  id: string;
  name: string;
  /** indexed-corpus document count ("N docs"). Omit for a plain folder (e.g. workspace). */
  docCount?: number;
  expanded: boolean;
  onToggle: () => void;
  /** derived from the folder's documents — lets a collapsed folder still signal activity.
   * Omit for a plain folder with no indexing aggregate. */
  aggregate?: FolderAggregate;
  /** when set, a "create subfolder" action appears on hover. */
  onCreateSubfolder?: () => void;
  /** when set, an "add file" (upload into this folder) action appears on hover. */
  onUpload?: () => void;
  /** when set, a "delete folder" action appears on hover (caller should confirm first). */
  onDelete?: () => void;
}

/**
 * A folder line in the collapsible tree. Carries an aggregate state so that —
 * tree collapsed — the user still sees where something is happening, without
 * opening every folder. The chevron+name area toggles; trailing actions/meta sit
 * outside that button so a "create subfolder" control can live on the row.
 */
export function FolderRow({
  id,
  name,
  docCount,
  expanded,
  onToggle,
  aggregate,
  onCreateSubfolder,
  onUpload,
  onDelete,
}: FolderRowProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.row}>
      <button
        type="button"
        className={styles.toggle}
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`folder-${id}`}
      >
        <span className={styles.chevron} data-expanded={expanded || undefined} aria-hidden>
          <Icon category="outlined" type="chevron_right" />
        </span>
        <span className={styles.folderIcon} aria-hidden>
          <Icon category="outlined" type="folder" />
        </span>
        <span className={styles.name} title={name}>
          {name}
        </span>
      </button>

      <div className={styles.trailing}>
        {(onUpload || onCreateSubfolder || onDelete) && (
          <span className={styles.actions}>
            {onUpload && (
              <IconButton
                color="on-surface"
                variant="icon"
                size="xs"
                icon={{ category: "outlined", type: "attach_file" }}
                aria-label={t("rework.resources.action.addFile")}
                title={t("rework.resources.action.addFile")}
                onClick={(e) => {
                  e.stopPropagation();
                  onUpload();
                }}
              />
            )}
            {onCreateSubfolder && (
              <IconButton
                color="on-surface"
                variant="icon"
                size="xs"
                icon={{ category: "outlined", type: "create_new_folder" }}
                aria-label={t("rework.resources.action.newSubfolder", { name })}
                title={t("rework.resources.action.newSubfolder", { name })}
                onClick={(e) => {
                  e.stopPropagation();
                  onCreateSubfolder();
                }}
              />
            )}
            {onDelete && (
              <DeleteIconButton
                size="xs"
                aria-label={t("rework.resources.action.delete")}
                title={t("rework.resources.action.delete")}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
              />
            )}
          </span>
        )}
        {docCount != null && (
          <span className={styles.count}>{t("rework.resources.folder.docCount", { count: docCount })}</span>
        )}
        {aggregate && <FolderAggregateBadge aggregate={aggregate} />}
      </div>
    </div>
  );
}

function FolderAggregateBadge({ aggregate }: { aggregate: FolderAggregate }) {
  const { t } = useTranslation();

  if (aggregate.processing > 0) {
    return (
      <span className={styles.aggregate} data-tone="processing">
        <span className={styles.pulseDot} aria-hidden />
        {t("rework.resources.folder.processing", { count: aggregate.processing })}
      </span>
    );
  }

  if (aggregate.failed > 0) {
    return (
      <span className={styles.aggregate} data-tone="failed">
        {t("rework.resources.folder.failed", { count: aggregate.failed })}
      </span>
    );
  }

  return (
    <span className={styles.aggregate} data-tone="ready">
      <Icon category="outlined" type="check_circle" />
      {t("rework.resources.folder.upToDate")}
    </span>
  );
}
