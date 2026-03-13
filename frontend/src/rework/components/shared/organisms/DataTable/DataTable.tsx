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
