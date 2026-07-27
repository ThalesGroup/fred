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
import Button from "@shared/atoms/Button/Button.tsx";
import styles from "./BulkActionsBar.module.css";

interface BulkActionsBarProps {
  selectedCount: number;
  onDelete: () => void;
  /** Corpus-only (RFC §13.9 — "exclure de la recherche" has no meaning for
   *  the other three tabs). Omit to hide the action entirely. */
  onExcludeFromSearch?: () => void;
}

/**
 * Contextual bulk-action buttons for the Resources explorer, shown next to
 * the create-folder/add-file icon buttons once at least one row is
 * selected (not a separate full-width bar — placement confirmed with the
 * team lead for this page specifically).
 */
export default function BulkActionsBar({ selectedCount, onDelete, onExcludeFromSearch }: BulkActionsBarProps) {
  const { t } = useTranslation();

  if (selectedCount === 0) return null;

  return (
    <div className={styles.bar}>
      <span className={styles.count}>{t("rework.resources.bulkActions.selectedCount", { count: selectedCount })}</span>
      {onExcludeFromSearch && (
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "search_off" }}
          onClick={onExcludeFromSearch}
        >
          {t("rework.resources.bulkActions.excludeFromSearch")}
        </Button>
      )}
      <Button
        color="error"
        variant="outlined"
        size="small"
        icon={{ category: "outlined", type: "delete" }}
        onClick={onDelete}
      >
        {t("rework.resources.bulkActions.delete")}
      </Button>
    </div>
  );
}
