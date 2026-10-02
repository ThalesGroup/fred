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
import IconButton from "../../atoms/IconButton/IconButton.tsx";
import Select from "../Select/Select.tsx";
import type { SelectOption } from "../Select/Select.tsx";

export interface TablePaginationLabels {
  totalItems: (count: number) => string;
  itemsPerPage: string;
  pageNumber: (page: number, pageCount: number) => string;
  first: string;
  prev: string;
  next: string;
  last: string;
}

const defaultLabels: TablePaginationLabels = {
  totalItems: (count) => `${count} items`,
  itemsPerPage: "Items per page",
  pageNumber: (page, pageCount) => `Page ${page} of ${pageCount}`,
  first: "First page",
  prev: "Previous page",
  next: "Next page",
  last: "Last page",
};

export interface TablePaginationProps {
  labels?: Partial<TablePaginationLabels>;
  totalItems: number;
  /** 0-based. */
  currentPage: number;
  pageCount: number;
  rowsPerPage: number;
  rowsPerPageOptions: SelectOption<number>[];
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
  labels,
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
  const text = { ...defaultLabels, ...labels };

  return (
    <div className={styles["datatable-footer"]}>
      <div className={styles["datatable-footer-left"]}>
        <span className={styles["footer-label"]}>{text.totalItems(totalItems)}</span>
      </div>
      <div className={styles["datatable-footer-right"]}>
        {onRowsPerPageChange && (
          <>
            <span className={styles["footer-label"]}>{text.itemsPerPage}</span>
            <div className={styles["footer-rows-per-page-select"]}>
              <Select<number>
                size="xs"
                compact
                ariaLabel={text.itemsPerPage}
                value={rowsPerPage}
                options={rowsPerPageOptions}
                onChange={onRowsPerPageChange}
              />
            </div>
          </>
        )}
        <div className={styles["footer-nav"]}>
          <IconButton
            type="button"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "first_page" }}
            aria-label={text.first}
            disabled={currentPage <= 0}
            onClick={onFirst}
          />
          <IconButton
            type="button"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "chevron_left" }}
            aria-label={text.prev}
            disabled={currentPage <= 0}
            onClick={onPrev}
          />
          <span className={`${styles["footer-label"]} ${styles["footer-page-label"]}`}>
            {text.pageNumber(currentPage + 1, pageCount)}
          </span>
          <IconButton
            type="button"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "chevron_right" }}
            aria-label={text.next}
            disabled={currentPage >= pageCount - 1}
            onClick={onNext}
          />
          <IconButton
            type="button"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "last_page" }}
            aria-label={text.last}
            disabled={currentPage >= pageCount - 1}
            onClick={onLast}
          />
        </div>
      </div>
    </div>
  );
}
