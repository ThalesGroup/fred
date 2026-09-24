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

/**
 * Translation between the resources table's sort header and the browse
 * contract's ordering fields.
 *
 * `DataTable` identifies a sorted column by its *rendered* label, which is
 * translated — so the mapping cannot be a static table here and takes a label
 * lookup instead, fed by the same `t()` calls the columns use.
 */

import type { SortState } from "@shared/molecules/DataTable/DataTable.tsx";
import type { BrowseDocumentsByTagRequest } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

/** The contract's own field names — never re-declared, read off the generated client. */
export type DocumentSortField = NonNullable<BrowseDocumentsByTagRequest["sort_by"]>;
export type DocumentSortOrder = NonNullable<BrowseDocumentsByTagRequest["sort_order"]>;

export interface DocumentOrdering {
  by: DocumentSortField;
  order: DocumentSortOrder;
}

/** Sortable columns, and the translation key each is labelled by. "Added by"
 *  is deliberately absent: `uploaded_by` is optional, so ordering on it would
 *  bunch every older or connector-pulled document at one end under a dash. */
export const SORTABLE_COLUMN_KEYS = {
  name: "rework.resources.columns.name",
  created: "rework.resources.columns.created",
  size: "rework.resources.columns.size",
} as const satisfies Record<DocumentSortField, string>;

const SORT_FIELDS = Object.keys(SORTABLE_COLUMN_KEYS) as DocumentSortField[];

/** Alphabetical by name, the file-explorer convention this table follows. */
export const DEFAULT_ORDERING: DocumentOrdering = { by: "name", order: "asc" };

export type ColumnLabel = (field: DocumentSortField) => string;

/**
 * There is no unsorted state to ask the server for — a page is always cut out
 * of some order — so the table is mounted with `sortClearable={false}` and the
 * active header only flips direction. `null` therefore never arrives from a
 * header press; it is handled as a fallback, alongside a label this module
 * does not know (a column renamed, or made sortable without being declared
 * above), and both return to the default ordering.
 */
export function orderingFromSortState(next: SortState | null, label: ColumnLabel): DocumentOrdering {
  if (!next) return DEFAULT_ORDERING;
  const field = SORT_FIELDS.find((candidate) => label(candidate) === next.columnLabel);
  return field ? { by: field, order: next.direction } : DEFAULT_ORDERING;
}

/** The arrow the header shows for the ordering currently in force. */
export function sortStateFromOrdering(ordering: DocumentOrdering, label: ColumnLabel): SortState {
  return { columnLabel: label(ordering.by), direction: ordering.order };
}
