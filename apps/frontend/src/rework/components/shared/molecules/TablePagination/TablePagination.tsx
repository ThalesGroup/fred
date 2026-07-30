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

import styles from "./TablePagination.module.scss";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { OptionModel } from "@models/Option.model.ts";

export interface TablePaginationProps {
  totalItems: number;
  /** 0-based. */
  currentPage: number;
  pageCount: number;
  rowsPerPage: number;
  rowsPerPageOptions: OptionModel<number>[];
  /** Omit to keep rowsPerPage fixed and hide the selector. */
  onRowsPerPageChange?: (value: number) => void;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onLast: () => void;
}

/**
 * Table footer: total-item count, an optional rows-per-page selector, and
 * first/prev/page-label/next/last navigation. Purely presentational — the
 * caller owns pagination state (client-side slicing or server offset/limit).
 * Extracted from DataTable's own inline footer so any table can reuse the
 * exact same bar (DataTable is the only current consumer, via its `pageSize`/
 * `serverPagination` props).
 */
export default function TablePagination({
  totalItems,
  currentPage,
  pageCount,
  rowsPerPage,
  rowsPerPageOptions,
  onRowsPerPageChange,
  onFirst,
  onPrev,
  onNext,
  onLast,
}: TablePaginationProps) {
  const { t } = useTranslation();

  return (
    <div className={styles["datatable-footer"]}>
      <div className={styles["datatable-footer-left"]}>
        <span className={styles["footer-label"]}>{t("dataTable.pagination.totalItems", { count: totalItems })}</span>
      </div>
      <div className={styles["datatable-footer-right"]}>
        {onRowsPerPageChange && (
          <>
            <span className={styles["footer-label"]}>{t("dataTable.pagination.itemsPerPage")}</span>
            <div className={styles["footer-rows-per-page-select"]}>
              <Select<number>
                size="small"
                compact
                value={rowsPerPage}
                options={rowsPerPageOptions}
                onChange={onRowsPerPageChange}
              />
            </div>
          </>
        )}
        <IconButton
          color="on-surface"
          variant="icon"
          size="medium"
          icon={{ category: "outlined", type: "first_page" }}
          aria-label={t("dataTable.pagination.first")}
          disabled={currentPage <= 0}
          onClick={onFirst}
        />
        <IconButton
          color="on-surface"
          variant="icon"
          size="medium"
          icon={{ category: "outlined", type: "chevron_left" }}
          aria-label={t("dataTable.pagination.prev")}
          disabled={currentPage <= 0}
          onClick={onPrev}
        />
        <span className={`${styles["footer-label"]} ${styles["footer-page-label"]}`}>
          {t("dataTable.pagination.pageNumber", { page: currentPage + 1, pageCount })}
        </span>
        <IconButton
          color="on-surface"
          variant="icon"
          size="medium"
          icon={{ category: "outlined", type: "chevron_right" }}
          aria-label={t("dataTable.pagination.next")}
          disabled={currentPage >= pageCount - 1}
          onClick={onNext}
        />
        <IconButton
          color="on-surface"
          variant="icon"
          size="medium"
          icon={{ category: "outlined", type: "last_page" }}
          aria-label={t("dataTable.pagination.last")}
          disabled={currentPage >= pageCount - 1}
          onClick={onLast}
        />
      </div>
    </div>
  );
}
