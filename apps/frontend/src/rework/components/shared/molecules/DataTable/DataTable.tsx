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
import React from "react";

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  backgroundColor?: string;
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
}: DataTableProps<T>) {
  const tableGridLayout = columns
    .map((column) => {
      return column.size ? `${column.size}` : "1fr";
    })
    .join(" ");

  return (
    <div
      className={styles["datatable-container"]}
      style={
        { "--grid-layout": tableGridLayout, "--datatable-background-color": backgroundColor } as React.CSSProperties
      }
    >
      {columns.map((column) => (
        <div className={`${styles["datatable-cell"]} ${styles["datatable-cell-header"]}`} key={column.label}>
          <span className={styles["header-content"]}>{column.label}</span>
        </div>
      ))}
      {data.map((line, lineIndex) => (
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
  );
}
