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
import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { MaterialIcon as Icon } from "../../atoms/Icon/Icon.tsx";
import Checkbox from "../../atoms/Checkbox/Checkbox.tsx";
import TablePagination from "../TablePagination/TablePagination.tsx";
import type { SelectOption } from "../Select/Select.tsx";
import type { TablePaginationLabels } from "../TablePagination/TablePagination.tsx";

const ROWS_PER_PAGE_OPTIONS = [20, 50, 100];

const EMBEDDED_CONTROL_SELECTOR = [
  "button, a, input, label, select, textarea, summary, audio[controls], video[controls], [tabindex]",
  '[contenteditable]:not([contenteditable="false" i])',
  ...[
    "button",
    "checkbox",
    "combobox",
    "grid",
    "link",
    "listbox",
    "menu",
    "menubar",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "radio",
    "radiogroup",
    "scrollbar",
    "searchbox",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "tablist",
    "textbox",
    "tree",
    "treegrid",
    "treeitem",
  ].map((role) => `[role~="${role}"]`),
].join(", ");

export type DataTableRowSize = "medium" | "small";

const ROW_HEIGHT_BY_SIZE: Record<DataTableRowSize, string> = {
  medium: "3rem" /* 48px */,
  small: "2.5rem" /* 40px */,
};

export type SortDirection = "asc" | "desc";
export interface SortState {
  columnLabel: string;
  direction: SortDirection;
}

/** Controlled, server-side pagination — pass together with a `data` array that
 *  already IS the current page's rows (the caller fetched them, e.g. via
 *  offset/limit). Omit for DataTable to paginate `data` itself in-memory via
 *  `pageSize`; the two are mutually exclusive (`serverPagination` wins). */
export interface ServerPagination {
  /** True row count across every page — not `data.length`, which is only this page. */
  totalCount: number;
  /** Current page's starting index (0-based), a multiple of limit. */
  offset: number;
  /** Rows per page, as already used for the `data` the caller fetched. */
  limit: number;
  onOffsetChange: (offset: number) => void;
  /** Wires up the rows-per-page selector. Omit to keep `limit` fixed and hide it. */
  onLimitChange?: (limit: number) => void;
}

export interface DataTableLabels {
  selectAllOnPage: string;
  /** String prefixes include the stable key; callbacks can resolve a human-readable identity. */
  selectRow: string | ((key: string | number) => string);
  sortColumn: (label: string, direction: SortDirection | null) => string;
  activateRow: string;
  pagination?: Partial<TablePaginationLabels>;
}

interface DataTableBaseProps<T> {
  labels?: Partial<DataTableLabels>;
  columns: DataTableColumn<T>[];
  data: T[];
  backgroundColor?: string;
  /** Extra left inset on the first column (header + every row), for tables
   *  whose content otherwise sits flush against the table's left edge. */
  firstColumnInset?: boolean;
  /** Overrides the row height (header + body, both become equal) — e.g.
   *  "2.5rem" for a denser table. Omit to keep each row type's own default
   *  height, unaffected — other DataTable call sites don't opt in. Takes
   *  precedence over `size` when both are given. */
  rowHeight?: string;
  /** Named row-height presets ("medium" = 48px, "small" = 40px), applied the
   *  same way as `rowHeight` (header + body become equal). Omit to keep each
   *  row type's own default height, unaffected — other DataTable call sites
   *  don't opt in. */
  size?: DataTableRowSize;
  /** Enables pagination and sets the initial rows-per-page (should be one of
   *  `ROWS_PER_PAGE_OPTIONS`). Omit to render every row with no pagination
   *  bar (default) — existing call sites are unaffected. Ignored when
   *  `serverPagination` is set. */
  pageSize?: number;
  /** Server-side pagination — see `ServerPagination`. Takes precedence over `pageSize`. */
  serverPagination?: ServerPagination;
  selectedKeys?: ReadonlySet<string | number>;
  onSelectionChange?: (keys: ReadonlySet<string | number>) => void;
  /** Activates the row background; embedded controls keep their own actions. */
  onRowClick?: (row: T) => void;
  /** Whether a third press on the sorted column clears the sort (default) or
   *  simply flips it back to ascending.
   *
   *  Clearing only means something when there is an unsorted order to return
   *  to — the `data` array's own. A server-ordered table has none: a page is
   *  always cut out of some order, so clearing would have to fall back to a
   *  default, and pressing one column's header would visibly move the sort to
   *  another column. Pass `false` there. */
  sortClearable?: boolean;
}

export type DataTableSortProps =
  | { sortState?: undefined; onSortChange?: undefined }
  | { sortState: SortState | null; onSortChange: (next: SortState | null) => void };

/** Selection requires stable keys so individual and page-wide actions share identity. */
export type DataTableProps<T> = DataTableBaseProps<T> &
  DataTableSortProps &
  (
    | {
        selectable?: false;
        /** Stable domain identity. Without it, object references (or primitive values) identify rows. */
        rowKey?: (element: T) => string | number;
      }
    | {
        selectable: boolean;
        selectedKeys: ReadonlySet<string | number>;
        onSelectionChange: (keys: ReadonlySet<string | number>) => void;
        /** Required when selection can be enabled, including a dynamic boolean. */
        rowKey: (element: T) => string | number;
      }
  );

export interface DataTableColumn<T> {
  label: string;
  /** A `grid-template-columns` track (e.g. "2fr", "6.5rem"). Avoid `"auto"`
   *  for a column whose header label and cell content differ meaningfully in
   *  width (e.g. an empty header over icon-button cells): the header and
   *  body render as two independent grids (so the header can sit outside
   *  the scrollable row area), and each grid resolves an `"auto"` track from
   *  only its own content — the header and body can disagree on that
   *  column's width, which then shows up as every column after it drifting
   *  out of alignment (the leftover space lands differently in whichever
   *  flexible `fr` column absorbs it). Prefer a fixed size sized to the
   *  cell's actual content instead. */
  size?: string;
  cellRenderer?: (element: T) => React.ReactNode;
  /** Enables click-to-sort on this column's header. */
  sortable?: boolean;
  /** Value compared when sorting this column client-side (uncontrolled
   *  mode — ignored when the table's sort is controlled via `onSortChange`,
   *  since the caller is then responsible for the order of `data`). */
  sortValue?: (element: T) => string | number | Date | null | undefined;
}

function compareSortValues(
  a: string | number | Date | null | undefined,
  b: string | number | Date | null | undefined,
): number {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  if (a instanceof Date || b instanceof Date) return new Date(a).getTime() - new Date(b).getTime();
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

export default function DataTable<T>({
  labels,
  columns,
  data,
  backgroundColor = "var(--surface-container)",
  firstColumnInset = false,
  rowHeight,
  size,
  pageSize,
  serverPagination,
  rowKey,
  selectable = false,
  selectedKeys,
  onSelectionChange,
  onRowClick,
  sortState: controlledSortState,
  onSortChange,
  sortClearable = true,
}: DataTableProps<T>) {
  const tableId = useId();
  const objectKeys = useRef(new WeakMap<object, number>());
  const primitiveKeys = useRef(new Map<unknown, number>());
  const nextObjectKey = useRef(0);
  const fallbackKey = (row: T): string => {
    if ((typeof row === "object" && row !== null) || typeof row === "function") {
      const object = row as object;
      let key = objectKeys.current.get(object);
      if (key === undefined) {
        key = nextObjectKey.current++;
        objectKeys.current.set(object, key);
      }
      return `object:${key}`;
    }
    let key = primitiveKeys.current.get(row);
    if (key === undefined) {
      key = nextObjectKey.current++;
      primitiveKeys.current.set(row, key);
    }
    return `primitive:${key}`;
  };
  if ((controlledSortState !== undefined) !== (onSortChange !== undefined)) {
    throw new Error("DataTable: sortState and onSortChange must be supplied together.");
  }
  if (selectable && selectedKeys === undefined) {
    throw new Error("DataTable: selectable requires selectedKeys.");
  }
  if (selectable && !onSelectionChange) {
    throw new Error("DataTable: selectable requires onSelectionChange.");
  }
  if (!onSortChange && columns.some((column) => column.sortable && !column.sortValue)) {
    throw new Error("DataTable: uncontrolled sortable columns require sortValue.");
  }
  for (const [name, value] of [
    ["pageSize", pageSize],
    ["serverPagination.limit", serverPagination?.limit],
  ] as const) {
    if (value !== undefined && (!Number.isSafeInteger(value) || value <= 0)) {
      throw new Error(`DataTable: ${name} must be a positive safe integer.`);
    }
  }
  if (serverPagination) {
    for (const [name, value] of [
      ["totalCount", serverPagination.totalCount],
      ["offset", serverPagination.offset],
    ] as const) {
      if (!Number.isSafeInteger(value) || value < 0) {
        throw new Error(`DataTable: serverPagination.${name} must be a nonnegative safe integer.`);
      }
    }
  }
  if (serverPagination && serverPagination.offset % serverPagination.limit !== 0) {
    throw new Error("DataTable: serverPagination.offset must be a multiple of limit.");
  }
  const paginationEnabled = pageSize !== undefined || serverPagination !== undefined;
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize ?? ROWS_PER_PAGE_OPTIONS[0]);
  const effectiveRowsPerPage = serverPagination ? serverPagination.limit : rowsPerPage;
  const rowsPerPageOptions: SelectOption<number>[] = ROWS_PER_PAGE_OPTIONS.map((value) => ({
    value,
    label: String(value),
    key: String(value),
  }));
  const [uncontrolledSortState, setUncontrolledSortState] = useState<SortState | null>(null);
  const sortIsControlled = onSortChange !== undefined;
  const sortState = sortIsControlled ? (controlledSortState ?? null) : uncontrolledSortState;

  const columnLabels = new Set<string>();
  const duplicateLabels = new Set<string>();
  for (const column of columns) {
    if (columnLabels.has(column.label)) duplicateLabels.add(column.label);
    columnLabels.add(column.label);
  }
  if (columns.some((column) => column.sortable && duplicateLabels.has(column.label))) {
    throw new Error("DataTable: sortable column labels must be unique across all columns.");
  }

  const sortedData = useMemo(() => {
    // Controlled sort: the caller already ordered `data` (e.g. a sorted
    // server response) — sorting it again here would fight that order.
    if (sortIsControlled || !sortState) return data;
    const column = columns.find((c) => c.label === sortState.columnLabel);
    if (!column?.sortValue) return data;
    const sorted = [...data].sort((a, b) => compareSortValues(column.sortValue!(a), column.sortValue!(b)));
    if (sortState.direction === "desc") sorted.reverse();
    return sorted;
  }, [data, sortState, sortIsControlled, columns]);

  const handleHeaderSortClick = (column: DataTableColumn<T>) => {
    if (!column.sortable) return;
    const isCurrent = sortState?.columnLabel === column.label;
    // Cycle asc -> desc -> unsorted, matching the small-header sort icon
    // convention (arrow visible only on the active column).
    const nextDirection: SortDirection | null = !isCurrent
      ? "asc"
      : sortState!.direction === "asc"
        ? "desc"
        : sortClearable
          ? null
          : "asc";
    const next: SortState | null = nextDirection ? { columnLabel: column.label, direction: nextDirection } : null;
    if (sortIsControlled) {
      onSortChange!(next);
    } else {
      setUncontrolledSortState(next);
    }
  };

  const pageCount = paginationEnabled
    ? Math.max(
        1,
        Math.ceil((serverPagination ? serverPagination.totalCount : sortedData.length) / effectiveRowsPerPage),
      )
    : 1;
  // Clamped rather than reset-on-change: if a row is removed and the current
  // page no longer exists, fall back to the new last page instead of jumping
  // the user back to page 1. Server-side pagination has no local `page` state
  // to clamp — the offset is the caller's source of truth, so the effect
  // below snaps it back through `onOffsetChange` instead (e.g. deleting every
  // row on a later page must not leave the caller re-fetching a stale,
  // now-out-of-range offset forever).
  const currentPage = serverPagination
    ? Math.floor(serverPagination.offset / serverPagination.limit)
    : Math.min(page, pageCount - 1);

  useEffect(() => {
    if (!serverPagination) return;
    const maxOffset =
      Math.max(0, Math.ceil(serverPagination.totalCount / serverPagination.limit) - 1) * serverPagination.limit;
    if (serverPagination.offset > maxOffset) {
      serverPagination.onOffsetChange(maxOffset);
    }
  }, [serverPagination]);
  // Server-paginated `data` already IS the current page's rows (the caller
  // fetched exactly that window) — slicing it again here would drop rows.
  const pageData =
    paginationEnabled && !serverPagination
      ? sortedData.slice(currentPage * rowsPerPage, currentPage * rowsPerPage + rowsPerPage)
      : sortedData;

  const goToPage = (targetPage: number) => {
    if (serverPagination) {
      serverPagination.onOffsetChange(targetPage * serverPagination.limit);
    } else {
      setPage(targetPage);
    }
  };

  const keyOccurrences = new Map<string, number>();
  const pageKeys = selectable && rowKey ? pageData.map((row) => rowKey(row)) : [];
  const selectedOnPageCount = pageKeys.filter((key) => selectedKeys?.has(key)).length;
  const allOnPageSelected = pageKeys.length > 0 && selectedOnPageCount === pageKeys.length;
  const someOnPageSelected = selectedOnPageCount > 0 && !allOnPageSelected;

  const toggleRow = (key: string | number) => {
    if (!onSelectionChange) return;
    const next = new Set(selectedKeys ?? []);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onSelectionChange(next);
  };

  const toggleAllOnPage = () => {
    if (!onSelectionChange) return;
    const next = new Set(selectedKeys ?? []);
    if (allOnPageSelected) pageKeys.forEach((key) => next.delete(key));
    else pageKeys.forEach((key) => next.add(key));
    onSelectionChange(next);
  };

  const tableGridLayout = [
    ...(selectable ? ["2.5rem"] : []),
    ...columns.map((column) => (column.size ? `${column.size}` : "1fr")),
  ].join(" ");

  const containerClasses = [styles["datatable-container"]];
  if (firstColumnInset) containerClasses.push(styles["first-column-inset"]);
  const resolvedRowHeight = rowHeight ?? (size ? ROW_HEIGHT_BY_SIZE[size] : undefined);

  return (
    <div
      className={containerClasses.join(" ")}
      style={
        {
          "--grid-layout": tableGridLayout,
          "--datatable-background-color": backgroundColor,
          ...(resolvedRowHeight ? { "--datatable-row-height": resolvedRowHeight } : {}),
        } as React.CSSProperties
      }
    >
      <div
        role="table"
        style={{ display: "contents" }}
        aria-rowcount={(serverPagination?.totalCount ?? data.length) + 1}
        aria-colcount={columns.length + (selectable ? 1 : 0)}
      >
        <div role="row" aria-rowindex={1} className={styles["datatable-header"]}>
          {selectable && (
            <div role="columnheader" className={`${styles["datatable-cell"]} ${styles["datatable-cell-select"]}`}>
              <Checkbox
                checked={allOnPageSelected}
                indeterminate={someOnPageSelected}
                onChange={toggleAllOnPage}
                aria-label={labels?.selectAllOnPage ?? "Select all on page"}
              />
            </div>
          )}
          {columns.map((column, columnIndex) => {
            const isSorted = sortState?.columnLabel === column.label;
            return (
              <div
                role="columnheader"
                aria-sort={
                  column.sortable
                    ? isSorted
                      ? sortState.direction === "asc"
                        ? "ascending"
                        : "descending"
                      : "none"
                    : undefined
                }
                className={styles["datatable-cell"]}
                key={columnIndex}
              >
                {column.sortable ? (
                  <button
                    type="button"
                    className={styles["header-sort-button"]}
                    aria-label={
                      labels?.sortColumn?.(column.label, isSorted ? sortState.direction : null) ??
                      `${column.label}, ${isSorted ? (sortState.direction === "asc" ? "ascending" : "descending") : "not sorted"}`
                    }
                    data-active={isSorted || undefined}
                    onClick={() => handleHeaderSortClick(column)}
                  >
                    <span className={styles["header-content"]}>{column.label}</span>
                    <span className={styles["sort-icon"]} data-visible={isSorted || undefined}>
                      {/* The arrow points the way the list runs, as a file
                        explorer does: down for ascending (A at the top, Z at
                        the bottom), up for descending. */}
                      <Icon type={isSorted && sortState?.direction === "desc" ? "arrow_upward" : "arrow_downward"} />
                    </span>
                  </button>
                ) : (
                  <span className={styles["header-content"]}>{column.label}</span>
                )}
              </div>
            );
          })}
        </div>
        <div role="rowgroup" className={styles["datatable-body"]}>
          {pageData.map((line, lineIndex) => {
            const identity = rowKey ? undefined : fallbackKey(line);
            const occurrence = identity === undefined ? 0 : (keyOccurrences.get(identity) ?? 0);
            if (identity !== undefined) keyOccurrences.set(identity, occurrence + 1);
            const key = rowKey ? rowKey(line) : `${identity}:${occurrence}`;
            const isSelected = selectable && (selectedKeys?.has(key) ?? false);
            return (
              <div
                role="row"
                aria-rowindex={
                  (serverPagination?.offset ?? (paginationEnabled ? currentPage * rowsPerPage : 0)) + lineIndex + 2
                }
                className={styles["datatable-row"]}
                key={`${typeof key}:${key}`}
                data-selected={isSelected || undefined}
                data-activatable={!!onRowClick || undefined}
                onClick={
                  onRowClick || selectable
                    ? (event) => {
                        const target = event.target as HTMLElement;
                        // Portaled cell controls bubble through React, outside the row's DOM.
                        if (!event.currentTarget.contains(target)) return;
                        const control = target.closest(EMBEDDED_CONTROL_SELECTOR);
                        if (control && control !== event.currentTarget && event.currentTarget.contains(control)) return;
                        if (onRowClick) onRowClick(line);
                        else toggleRow(key);
                      }
                    : undefined
                }
              >
                {selectable && (
                  <div role="cell" className={`${styles["datatable-cell"]} ${styles["datatable-cell-select"]}`}>
                    <Checkbox
                      checked={selectedKeys?.has(key) ?? false}
                      onChange={() => toggleRow(key)}
                      aria-label={
                        typeof labels?.selectRow === "function"
                          ? labels.selectRow(key)
                          : `${labels?.selectRow ?? "Select row"} ${key}`
                      }
                    />
                  </div>
                )}
                {columns.map((column, columnIndex) => {
                  const cellContent = column.cellRenderer?.(line);
                  const isPrimitive = typeof cellContent === "string" || typeof cellContent === "number";
                  return (
                    <div role="cell" className={styles["datatable-cell"]} key={columnIndex}>
                      {/* Primitive cell values get single-line ellipsis
                       * truncation, with the full value readable via the
                       * native title tooltip — free-length text (usernames,
                       * team names) must never spill under the neighbouring
                       * column. Element values are the caller's own layout
                       * and pass through untouched. */}
                      {onRowClick && columnIndex === 0 && (
                        <button
                          type="button"
                          data-row-action
                          className={styles["row-action"]}
                          aria-label={labels?.activateRow ?? "Activate row"}
                          aria-describedby={`${tableId}-${lineIndex}-content`}
                          onClick={() => onRowClick(line)}
                        >
                          <Icon type="chevron_right" />
                        </button>
                      )}
                      <div
                        id={columnIndex === 0 ? `${tableId}-${lineIndex}-content` : undefined}
                        className={styles["cell-content"]}
                      >
                        {isPrimitive ? (
                          <span className={styles["cell-text"]} title={String(cellContent)}>
                            {cellContent}
                          </span>
                        ) : (
                          cellContent
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
      {paginationEnabled && (
        <TablePagination
          labels={labels?.pagination}
          totalItems={serverPagination ? serverPagination.totalCount : data.length}
          currentPage={currentPage}
          pageCount={pageCount}
          rowsPerPage={effectiveRowsPerPage}
          rowsPerPageOptions={rowsPerPageOptions}
          onRowsPerPageChange={
            !serverPagination || serverPagination.onLimitChange
              ? (value) => {
                  if (serverPagination?.onLimitChange) {
                    serverPagination.onOffsetChange(0);
                    serverPagination.onLimitChange(value);
                  } else {
                    setRowsPerPage(value);
                    setPage(0);
                  }
                }
              : undefined
          }
          onFirst={() => goToPage(0)}
          onPrev={() => goToPage(currentPage - 1)}
          onNext={() => goToPage(currentPage + 1)}
          onLast={() => goToPage(pageCount - 1)}
        />
      )}
    </div>
  );
}
