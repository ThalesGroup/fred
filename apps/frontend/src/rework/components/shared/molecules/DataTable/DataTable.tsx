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

import styles from "./DataTable.module.scss";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { OptionModel } from "@models/Option.model.ts";

const ROWS_PER_PAGE_OPTIONS = [20, 50, 100];

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  backgroundColor?: string;
  /** Extra left inset on the first column (header + every row), for tables
   *  whose content otherwise sits flush against the table's left edge. */
  firstColumnInset?: boolean;
  /** Enables pagination and sets the initial rows-per-page (should be one of
   *  `ROWS_PER_PAGE_OPTIONS`). Omit to render every row with no pagination
   *  bar (default) — existing call sites are unaffected. */
  pageSize?: number;
}

export interface DataTableColumn<T> {
  label: string;
  size?: string;
  cellRenderer?: (element: T) => React.ReactNode;
}

const rowsPerPageOptions: OptionModel<number>[] = ROWS_PER_PAGE_OPTIONS.map((n) => ({
  value: n,
  label: String(n),
  key: String(n),
}));

export default function DataTable<T>({
  columns,
  data,
  backgroundColor = "var(--surface-container)",
  firstColumnInset = false,
  pageSize,
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const paginationEnabled = pageSize !== undefined;
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize ?? ROWS_PER_PAGE_OPTIONS[0]);

  const pageCount = paginationEnabled ? Math.max(1, Math.ceil(data.length / rowsPerPage)) : 1;
  // Clamped rather than reset-on-change: if a row is removed and the current
  // page no longer exists, fall back to the new last page instead of jumping
  // the user back to page 1.
  const currentPage = Math.min(page, pageCount - 1);
  const pageData = paginationEnabled
    ? data.slice(currentPage * rowsPerPage, currentPage * rowsPerPage + rowsPerPage)
    : data;

  const tableGridLayout = columns
    .map((column) => {
      return column.size ? `${column.size}` : "1fr";
    })
    .join(" ");

  const containerClasses = [styles["datatable-container"]];
  if (firstColumnInset) containerClasses.push(styles["first-column-inset"]);

  return (
    <div
      className={containerClasses.join(" ")}
      style={
        { "--grid-layout": tableGridLayout, "--datatable-background-color": backgroundColor } as React.CSSProperties
      }
    >
      <div className={styles["datatable-body"]}>
        {columns.map((column) => (
          <div className={`${styles["datatable-cell"]} ${styles["datatable-cell-header"]}`} key={column.label}>
            <span className={styles["header-content"]}>{column.label}</span>
          </div>
        ))}
        {pageData.map((line, lineIndex) => (
          <div className={styles["datatable-row"]} key={`row-${lineIndex}`}>
            {columns.map((column) => {
              return (
                <div className={styles["datatable-cell"]} key={column.label}>
                  {column.cellRenderer(line)}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      {paginationEnabled && (
        <div className={styles["datatable-footer"]}>
          <div className={styles["datatable-footer-left"]}>
            <span className={styles["footer-label"]}>
              {t("dataTable.pagination.totalItems", { count: data.length })}
            </span>
          </div>
          <div className={styles["datatable-footer-right"]}>
            <Select<number>
              size="small"
              compact
              value={rowsPerPage}
              options={rowsPerPageOptions}
              onChange={(value) => {
                setRowsPerPage(value);
                setPage(0);
              }}
            />
            <IconButton
              color="on-surface"
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "first_page" }}
              aria-label={t("dataTable.pagination.first")}
              disabled={currentPage <= 0}
              onClick={() => setPage(0)}
            />
            <IconButton
              color="on-surface"
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "chevron_left" }}
              aria-label={t("dataTable.pagination.prev")}
              disabled={currentPage <= 0}
              onClick={() => setPage(currentPage - 1)}
            />
            <span className={`${styles["footer-label"]} ${styles["footer-page-label"]}`}>
              {t("dataTable.pagination.pageNumber", { page: currentPage + 1 })}
            </span>
            <IconButton
              color="on-surface"
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "chevron_right" }}
              aria-label={t("dataTable.pagination.next")}
              disabled={currentPage >= pageCount - 1}
              onClick={() => setPage(currentPage + 1)}
            />
            <IconButton
              color="on-surface"
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "last_page" }}
              aria-label={t("dataTable.pagination.last")}
              disabled={currentPage >= pageCount - 1}
              onClick={() => setPage(pageCount - 1)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
