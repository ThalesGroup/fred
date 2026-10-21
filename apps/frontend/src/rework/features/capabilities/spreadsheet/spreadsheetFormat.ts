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

// Locale-aware display of preview cells, close to what Excel shows for the
// number formats the backend wrote (fixed decimals, currency symbol, percent).
// Intl formatters are costly to build: one set per column, one pass per sheet.

import type { SpreadsheetCell, SpreadsheetColumn, SpreadsheetSheet } from "./types";

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Numbers and dates align right, like in Excel. */
export function isRightAligned(column: SpreadsheetColumn): boolean {
  return column.type !== "text";
}

function numberFormat(column: SpreadsheetColumn, locale: string, decimals: number): Intl.NumberFormat {
  const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
  if (column.type === "percent") return new Intl.NumberFormat(locale, { ...digits, style: "percent" });
  if (column.type === "currency" && column.currency) {
    return new Intl.NumberFormat(locale, { ...digits, style: "currency", currency: column.currency });
  }
  return new Intl.NumberFormat(locale, digits);
}

export interface ColumnFormatter {
  cell: (value: SpreadsheetCell) => string;
  /** A total keeps its column's format, except a count (whole) and an integer average. */
  total: (value: SpreadsheetCell) => string;
}

export function columnFormatter(column: SpreadsheetColumn, locale: string): ColumnFormatter {
  const main = numberFormat(column, locale, column.decimals ?? 0);
  const dates =
    column.type === "date"
      ? new Intl.DateTimeFormat(locale, { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit" })
      : null;
  const totals =
    column.total === "count"
      ? new Intl.NumberFormat(locale)
      : column.total === "average" && column.type === "integer"
        ? numberFormat(column, locale, 2)
        : null;

  const cell = (value: SpreadsheetCell): string => {
    if (value === null || value === undefined) return "";
    if (dates && typeof value === "string") {
      const match = ISO_DATE.exec(value);
      return match ? dates.format(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))) : value;
    }
    return typeof value === "number" ? main.format(value) : String(value);
  };
  const total = (value: SpreadsheetCell): string => {
    if (typeof value !== "number") return value ?? "";
    return totals ? totals.format(value) : cell(value);
  };
  return { cell, total };
}

/** Excel column letters: 0 -> A, 25 -> Z, 26 -> AA. */
export function columnLetter(index: number): string {
  let letters = "";
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) {
    letters = String.fromCharCode(65 + ((n - 1) % 26)) + letters;
  }
  return letters;
}

const MIN_WIDTH = 6;
const MAX_WIDTH = 60;

export interface ColumnLayout {
  /** Width in characters, the unit Excel column widths use. */
  width: number;
  /** A text column longer than the widest column wraps instead of cutting. */
  wrap: boolean;
}

export interface FormattedSheet {
  rows: string[][];
  totals: string[] | null;
  layouts: ColumnLayout[];
}

/** Formats every cell once and sizes columns like the workbook writer (longest value + 2, capped). */
export function formatSheet(sheet: SpreadsheetSheet, locale: string): FormattedSheet {
  const formatters = sheet.columns.map((column) => columnFormatter(column, locale));
  const rows = sheet.rows.map((row) => formatters.map((format, index) => format.cell(row[index] ?? null)));
  const totals = sheet.totals ? formatters.map((format, index) => format.total(sheet.totals?.[index] ?? null)) : null;
  const layouts = sheet.columns.map((column, index) => {
    let longest = column.header.length;
    for (const row of rows) longest = Math.max(longest, row[index].length);
    if (totals) longest = Math.max(longest, totals[index].length);
    const width = Math.min(Math.max(longest + 2, MIN_WIDTH), MAX_WIDTH);
    return { width, wrap: column.type === "text" && longest + 2 > MAX_WIDTH };
  });
  return { rows, totals, layouts };
}

/**
 * True when the text may be cut by its column, so the cell needs a tooltip. Widths
 * are in `ch` but glyphs are proportional: text near the column width can clip.
 */
export function mayClip(text: string, layout: ColumnLayout | undefined): boolean {
  return !!layout && !layout.wrap && text.length > 0 && text.length + 4 > layout.width;
}
