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

import { useRef, type ReactNode } from "react";
import { Breadcrumb, type BreadcrumbSegment } from "@shared/molecules/Breadcrumb/Breadcrumb.tsx";
import DataTable, { type DataTableColumn, type ServerPagination } from "@shared/molecules/DataTable/DataTable.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import styles from "./ResourceExplorer.module.css";

export interface ResourceExplorerBreadcrumbProps {
  segments: BreadcrumbSegment[];
  onBack: () => void;
  /** False at the navigation root — the back button stays mounted (reserving
   * its layout space so the breadcrumb never shifts) but renders disabled
   * and invisible rather than being unmounted. */
  canGoBack: boolean;
  /** Used as both the button's aria-label and its hover tooltip text. */
  backLabel: string;
}

export interface ResourceExplorerSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel: string;
  clearAriaLabel: string;
}

export interface ResourceExplorerProps<T> {
  breadcrumb: ResourceExplorerBreadcrumbProps;
  /** Omit to hide the search box entirely (a tab that doesn't need one yet).
   * Filtering is caller-owned — `rows` must already be filtered; this only
   * renders the input and reports its value back. */
  search?: ResourceExplorerSearchProps;
  /** Caller-owned content rendered in the toolbar's trailing group, before
   * the search box — e.g. a bulk-actions bar and/or new-folder/upload
   * buttons. Opaque to this component. */
  toolbarActions?: ReactNode;
  /** Loading takes precedence over empty; both take precedence over the table. */
  loading?: boolean;
  loadingMessage?: ReactNode;
  empty?: boolean;
  emptyMessage?: ReactNode;
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  selectable?: boolean;
  selectedKeys?: ReadonlySet<string | number>;
  onSelectedKeysChange?: (keys: ReadonlySet<string | number>) => void;
  /** Mutually exclusive with `pageSize` — same contract as DataTable. */
  serverPagination?: ServerPagination;
  pageSize?: number;
  rowHeight?: string;
  firstColumnInset?: boolean;
  tableBackgroundColor?: string;
}

/**
 * The reusable "card with a header and a table" shell behind the Resources
 * page's tabs: a toolbar (back button, breadcrumb, caller-supplied actions,
 * an optional search box) above a DataTable, with loading/empty states in
 * between. Extracted from the Corpus d'équipe tab (FRONT-09.H/RFC §13.7) so
 * the other three tabs (Mon espace/Espace d'équipe/Agents) can eventually
 * get the same rich table instead of their current single-line rows —
 * this component itself has no idea what a "document" or a "tag" is:
 * rows, columns, and every cell's rendering are entirely caller-supplied.
 */
export default function ResourceExplorer<T>({
  breadcrumb,
  search,
  toolbarActions,
  loading = false,
  loadingMessage,
  empty = false,
  emptyMessage,
  columns,
  rows,
  rowKey,
  selectable = true,
  selectedKeys,
  onSelectedKeysChange,
  serverPagination,
  pageSize,
  rowHeight = "2.5rem",
  firstColumnInset = true,
  tableBackgroundColor = "var(--surface-container-high)",
}: ResourceExplorerProps<T>) {
  const searchInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className={styles.card}>
      <div className={styles.toolbar}>
        <span className={styles.toolbarStart}>
          <Tooltip text={breadcrumb.backLabel}>
            <IconButton
              color="on-surface-retreat"
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "arrow_back" }}
              aria-label={breadcrumb.backLabel}
              disabled={!breadcrumb.canGoBack}
              style={!breadcrumb.canGoBack ? { visibility: "hidden" } : undefined}
              onClick={breadcrumb.onBack}
            />
          </Tooltip>
          <Breadcrumb segments={breadcrumb.segments} />
        </span>
        <span className={styles.toolbarEnd}>
          {toolbarActions}
          {search && (
            <span className={styles.search}>
              <TextInput
                ref={searchInputRef}
                compact
                size="small"
                icon={{ category: "outlined", type: "search" }}
                value={search.value}
                onChange={(e) => search.onChange(e.target.value)}
                placeholder={search.placeholder}
                aria-label={search.ariaLabel}
                style={
                  search.value ? { paddingRight: "calc(var(--spacing-2xs) + 2rem + var(--spacing-xs))" } : undefined
                }
              />
              {search.value && (
                <span className={styles.searchClear}>
                  <IconButton
                    type="button"
                    size="small"
                    color="on-surface-retreat"
                    variant="icon"
                    icon={{ category: "outlined", type: "close" }}
                    aria-label={search.clearAriaLabel}
                    onClick={() => {
                      search.onChange("");
                      searchInputRef.current?.focus();
                    }}
                  />
                </span>
              )}
            </span>
          )}
        </span>
      </div>

      {loading ? (
        <div className={`${styles.hint} ${styles.loadingHint}`}>
          <Spinner size={16} />
          {loadingMessage}
        </div>
      ) : empty ? (
        <div className={styles.hint}>{emptyMessage}</div>
      ) : (
        <div className={styles.tableFill}>
          <DataTable<T>
            columns={columns}
            data={rows}
            rowKey={rowKey}
            rowHeight={rowHeight}
            firstColumnInset={firstColumnInset}
            selectable={selectable}
            selectedKeys={selectedKeys}
            onSelectionChange={onSelectedKeysChange}
            backgroundColor={tableBackgroundColor}
            serverPagination={serverPagination}
            pageSize={pageSize}
          />
        </div>
      )}
    </div>
  );
}
