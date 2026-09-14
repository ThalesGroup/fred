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
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import Checkbox from "@shared/atoms/Checkbox/Checkbox.tsx";
import TablePagination from "@shared/molecules/TablePagination/TablePagination.tsx";
import { OptionModel } from "@models/Option.model.ts";

const ROWS_PER_PAGE_OPTIONS = [20, 50, 100];

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
  /** Current page's starting index (0-based). */
  offset: number;
  /** Rows per page, as already used for the `data` the caller fetched. */
  limit: number;
  onOffsetChange: (offset: number) => void;
  /** Wires up the rows-per-page selector. Omit to keep `limit` fixed and hide it. */
  onLimitChange?: (limit: number) => void;
}

interface DataTableProps<T> {
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
  /** Stable per-row identity, e.g. `(member) => member.user.id`. Omit only
   *  for data that never reorders between renders — without it, React falls
   *  back to array index as key, which misattributes any row-scoped
   *  component state (open menus, in-flight click handlers) to the wrong
   *  item as soon as `data` re-sorts (e.g. after an edit changes sort
   *  order). Required when `selectable` is set. */
  rowKey?: (element: T) => string | number;
  /** Adds a leading checkbox column. Selection is scoped to the checkbox
   *  itself (not the whole row) — rows here typically carry their own
   *  clickable actions (preview, menu), so a whole-row click target would
   *  fight with those instead of being an unambiguous convenience. */
  selectable?: boolean;
  selectedKeys?: ReadonlySet<string | number>;
  onSelectionChange?: (keys: ReadonlySet<string | number>) => void;
  /** Controlled sort — pass together with `onSortChange` when the caller
   *  re-fetches/re-sorts `data` itself (e.g. server-side sort). Omit both
   *  for DataTable to sort `data` internally using each column's
   *  `sortValue`. */
  sortState?: SortState | null;
  onSortChange?: (next: SortState | null) => void;
}

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
  rowHeight,
  size,
  pageSize,
  serverPagination,
  rowKey,
  selectable = false,
  selectedKeys,
  onSelectionChange,
  sortState: controlledSortState,
  onSortChange,
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const paginationEnabled = pageSize !== undefined || serverPagination !== undefined;
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize ?? ROWS_PER_PAGE_OPTIONS[0]);
  const effectiveRowsPerPage = serverPagination ? serverPagination.limit : rowsPerPage;
  const [uncontrolledSortState, setUncontrolledSortState] = useState<SortState | null>(null);
  const sortIsControlled = onSortChange !== undefined;
  const sortState = sortIsControlled ? (controlledSortState ?? null) : uncontrolledSortState;

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
    const nextDirection: SortDirection | null = !isCurrent ? "asc" : sortState!.direction === "asc" ? "desc" : null;
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
      <div className={styles["datatable-header"]}>
        {selectable && (
          <div className={`${styles["datatable-cell"]} ${styles["datatable-cell-select"]}`}>
            <Checkbox
              checked={allOnPageSelected}
              indeterminate={someOnPageSelected}
              onChange={toggleAllOnPage}
              aria-label={t("dataTable.selection.selectAllOnPage")}
            />
          </div>
        )}
        {columns.map((column, columnIndex) => {
          const isSorted = sortState?.columnLabel === column.label;
          return (
            <div className={styles["datatable-cell"]} key={columnIndex}>
              {column.sortable ? (
                <button
                  type="button"
                  className={styles["header-sort-button"]}
                  data-active={isSorted || undefined}
                  onClick={() => handleHeaderSortClick(column)}
                >
                  <span className={styles["header-content"]}>{column.label}</span>
                  <span className={styles["sort-icon"]} data-visible={isSorted || undefined}>
                    <Icon
                      category="outlined"
                      type={isSorted && sortState?.direction === "desc" ? "arrow_downward" : "arrow_upward"}
                    />
                  </span>
                </button>
              ) : (
                <span className={styles["header-content"]}>{column.label}</span>
              )}
            </div>
          );
        })}
      </div>
      <div className={styles["datatable-body"]}>
        {pageData.map((line, lineIndex) => {
          const key = rowKey ? rowKey(line) : lineIndex;
          const isSelected = selectable && (selectedKeys?.has(key) ?? false);
          return (
            <div
              className={styles["datatable-row"]}
              key={key}
              data-selected={isSelected || undefined}
              onClick={
                selectable
                  ? (event) => {
                      // Clicking an interactive control inside the row (a
                      // preview button, a folder-name link, the checkbox
                      // itself) must do its own thing, not also toggle
                      // selection — only the row's otherwise-inert
                      // background counts as "select this row". `label`
                      // matters here specifically for the Checkbox atom: its
                      // native input is visually hidden and wrapped in a
                      // <label>, so a real click lands on the label/box, not
                      // the input directly — the browser then separately
                      // forwards a synthetic click to the input itself. Not
                      // excluding `label` here meant this handler fired on
                      // the first (visible) click AND the checkbox's own
                      // onChange fired on the forwarded one: two toggles
                      // that cancel out, looking like the click did nothing.
                      const target = event.target as HTMLElement;
                      if (target.closest('button, a, input, label, [role="menuitem"]')) return;
                      toggleRow(key);
                    }
                  : undefined
              }
            >
              {selectable && (
                <div className={`${styles["datatable-cell"]} ${styles["datatable-cell-select"]}`}>
                  <Checkbox
                    checked={selectedKeys?.has(key) ?? false}
                    onChange={() => toggleRow(key)}
                    aria-label={t("dataTable.selection.selectRow")}
                  />
                </div>
              )}
              {columns.map((column, columnIndex) => {
                const cellContent = column.cellRenderer?.(line);
                const isPrimitive = typeof cellContent === "string" || typeof cellContent === "number";
                return (
                  <div className={styles["datatable-cell"]} key={columnIndex}>
                    {/* Primitive cell values get single-line ellipsis
                     * truncation, with the full value readable via the
                     * native title tooltip — free-length text (usernames,
                     * team names) must never spill under the neighbouring
                     * column. Element values are the caller's own layout
                     * and pass through untouched. */}
                    {isPrimitive ? (
                      <span className={styles["cell-text"]} title={String(cellContent)}>
                        {cellContent}
                      </span>
                    ) : (
                      cellContent
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
      {paginationEnabled && (
        <TablePagination
          totalItems={serverPagination ? serverPagination.totalCount : data.length}
          currentPage={currentPage}
          pageCount={pageCount}
          rowsPerPage={effectiveRowsPerPage}
          rowsPerPageOptions={rowsPerPageOptions}
          onRowsPerPageChange={
            !serverPagination || serverPagination.onLimitChange
              ? (value) => {
                  if (serverPagination?.onLimitChange) {
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
