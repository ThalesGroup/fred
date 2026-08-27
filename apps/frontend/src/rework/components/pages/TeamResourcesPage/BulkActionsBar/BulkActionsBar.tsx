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
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import styles from "./BulkActionsBar.module.css";

interface BulkActionsBarProps {
  selectedCount: number;
  onDelete: () => void;
  /** Clears the current row selection — swaps this whole bar back out for
   *  the create-folder/add-file toolbar. */
  onClearSelection: () => void;
  /** Corpus-only (RFC §13.9 — "exclure de la recherche" has no meaning for
   *  the other three tabs). `mode` picks the button's direction: "exclude"
   *  when every selected doc is currently searchable, "include" when every
   *  one is already excluded. Omit to hide the action entirely — including
   *  on a mixed selection (some excluded, some not), where there's no single
   *  unambiguous direction to offer. `loading` shows the same in-button
   *  spinner as `downloadLoading`: a folder-containing selection resolves its
   *  descendant documents on click before toggling them (#2446), which reads
   *  as a dead click otherwise. */
  searchToggle?: { mode: "exclude" | "include"; onClick: () => void; loading?: boolean };
  /** One file downloads directly; 2+ download as a single ZIP (RFC §13.13,
   *  client-side). Omit to hide the action — e.g. a folders-only selection
   *  on `FilesystemWorkspace`, which has nothing downloadable selected. */
  onDownload?: () => void;
  /** True while `onDownload`'s zip is being fetched/built — every file's
   *  blob has to round-trip through the browser first (RFC §13.13), which
   *  reads as a dead click without this: swaps the icon for a spinner and
   *  disables the button instead of leaving it looking unresponsive. */
  downloadLoading?: boolean;
  /** True while a folder-containing delete is in flight — deleting a folder
   *  cascades server-side and, with several folders selected, the round-trips
   *  add up (#2446). Same in-button spinner as `downloadLoading`. */
  deleteLoading?: boolean;
}

/**
 * Contextual bulk-action buttons for the Resources explorer, shown next to
 * the create-folder/add-file icon buttons once at least one row is
 * selected (not a separate full-width bar — placement confirmed with the
 * team lead for this page specifically).
 */
export default function BulkActionsBar({
  selectedCount,
  onDelete,
  onClearSelection,
  searchToggle,
  onDownload,
  downloadLoading = false,
  deleteLoading = false,
}: BulkActionsBarProps) {
  const { t } = useTranslation();

  if (selectedCount === 0) return null;

  return (
    <div className={styles.bar}>
      <span className={styles.count}>{t("rework.resources.bulkActions.selectedCount", { count: selectedCount })}</span>
      {searchToggle &&
        (() => {
          const key =
            searchToggle.mode === "exclude"
              ? "rework.resources.bulkActions.excludeFromSearch"
              : "rework.resources.bulkActions.includeInSearch";
          return (
            <Tooltip text={t(key)}>
              <IconButton
                variant="outlined"
                size="small"
                icon={{ category: "outlined", type: searchToggle.mode === "exclude" ? "search_off" : "search" }}
                aria-label={t(key)}
                loading={searchToggle.loading}
                onClick={searchToggle.onClick}
              />
            </Tooltip>
          );
        })()}
      {onDownload && (
        <Tooltip text={t("rework.resources.bulkActions.download")}>
          <IconButton
            variant="outlined"
            size="small"
            icon={{ category: "outlined", type: "download" }}
            aria-label={t("rework.resources.bulkActions.download")}
            loading={downloadLoading}
            onClick={onDownload}
          />
        </Tooltip>
      )}
      <Tooltip text={t("rework.resources.bulkActions.delete")}>
        <IconButton
          color="error"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "delete" }}
          aria-label={t("rework.resources.bulkActions.delete")}
          loading={deleteLoading}
          onClick={onDelete}
        />
      </Tooltip>
      <Tooltip text={t("rework.resources.bulkActions.clearSelection")}>
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          aria-label={t("rework.resources.bulkActions.clearSelection")}
          onClick={onClearSelection}
        />
      </Tooltip>
    </div>
  );
}
