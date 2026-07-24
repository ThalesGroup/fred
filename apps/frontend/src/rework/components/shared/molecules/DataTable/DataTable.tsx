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

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  backgroundColor?: string;
  /** Extra left inset on the first column (header + every row), for tables
   *  whose content otherwise sits flush against the table's left edge. */
  firstColumnInset?: boolean;
  /** Rows per page. Omit to render every row with no pagination (default). */
  pageSize?: number;
}

export interface DataTableColumn<T> {
  label: string;
  size?: string;
  cellRenderer?: (element: T) => React.ReactNode;
}

export default function DataTable<T>({
  columns,
  data,
  backgroundColor = "var(--surface-container)",
  firstColumnInset = false,
  pageSize,
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const [page, setPage] = useState(0);

  const pageCount = pageSize ? Math.max(1, Math.ceil(data.length / pageSize)) : 1;
  // Clamped rather than reset-on-change: if a row is removed and the current
  // page no longer exists, fall back to the new last page instead of jumping
  // the user back to page 1.
  const currentPage = Math.min(page, pageCount - 1);
  const pageData = pageSize ? data.slice(currentPage * pageSize, currentPage * pageSize + pageSize) : data;

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
      {pageSize && pageCount > 1 && (
        <div className={styles["datatable-footer"]}>
          <IconButton
            color="on-surface"
            variant="icon"
            size="xs"
            icon={{ category: "outlined", type: "chevron_left" }}
            aria-label={t("dataTable.pagination.prev")}
            disabled={currentPage <= 0}
            onClick={() => setPage(currentPage - 1)}
          />
          <span className={styles["footer-label"]}>
            {t("dataTable.pagination.page", { page: currentPage + 1, pageCount })}
          </span>
          <IconButton
            color="on-surface"
            variant="icon"
            size="xs"
            icon={{ category: "outlined", type: "chevron_right" }}
            aria-label={t("dataTable.pagination.next")}
            disabled={currentPage >= pageCount - 1}
            onClick={() => setPage(currentPage + 1)}
          />
        </div>
      )}
    </div>
  );
}
