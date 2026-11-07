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

// Shapes of the `spreadsheet_preview` chat part and of the JSON preview it points
// at, both written by the backend `spreadsheet` capability.

export const CAPABILITY_ID = "spreadsheet";
export const PANE_WIDGET = "spreadsheet_pane";

export interface SpreadsheetPreviewPartData {
  type: "spreadsheet_preview";
  /** Storage key of the `.xlsx`; unique per created file. */
  preview_id: string;
  file_name: string;
  /** Bearer-protected `/fs/download` hrefs: fetch them with the Authorization header. */
  xlsx_download_url: string;
  preview_url: string;
  /** Versions of one workbook share this id; absent on files created before versions. */
  workbook_id?: string;
  version?: number;
}

export type SpreadsheetColumnType = "text" | "number" | "integer" | "percent" | "currency" | "date";
export type SpreadsheetTotalKind = "sum" | "average" | "min" | "max" | "count";
export type SpreadsheetCell = string | number | null;

export interface SpreadsheetColumn {
  header: string;
  type: SpreadsheetColumnType;
  /** Decimals the Excel number format shows; numeric columns only. */
  decimals?: number;
  currency?: string;
  total?: SpreadsheetTotalKind;
  /** Formula column: its Excel formula, with `{row}` standing for the row number. */
  formula?: string;
  /** The totals row's Excel formula for this column. */
  total_formula?: string;
}

export interface SpreadsheetSheet {
  name: string;
  columns: SpreadsheetColumn[];
  /** Typed values (dates as YYYY-MM-DD), capped server-side. */
  rows: SpreadsheetCell[][];
  /** Rows in the file, which can exceed `rows.length`. */
  row_count: number;
  /** Computed totals row (the label cell names its functions), or null. */
  totals: SpreadsheetCell[] | null;
  /** Formulas of single cells (and of columns reading other rows), by A1 address. */
  cell_formulas?: Record<string, string>;
}

export interface SpreadsheetPreview {
  version: number;
  sheets: SpreadsheetSheet[];
  /** Build date (YYYY-MM-DD) when values read TODAY or NOW. */
  computed_at?: string;
}
