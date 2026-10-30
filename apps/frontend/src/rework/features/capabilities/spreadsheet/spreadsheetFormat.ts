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

const ROW_PLACEHOLDER = /\{row\}/g;

/** The formula of a computed, own-formula or totals cell, else null. */
export function cellFormula(sheet: SpreadsheetSheet, row: number, column: number): string | null {
  const spec = sheet.columns[column];
  if (!spec || row === 1) return null;
  if (row === sheet.row_count + 2 && sheet.totals) return spec.total_formula ?? null;
  const own = sheet.cell_formulas?.[`${columnLetter(column)}${row}`];
  if (own) return own;
  return spec.formula ? spec.formula.replace(ROW_PLACEHOLDER, String(row)) : null;
}

/**
 * What Excel's formula bar shows for a cell: the formula of a computed or totals
 * cell, else the typed value unformatted (no grouping or symbol, percent as "15%").
 */
export function formulaBarText(
  sheet: SpreadsheetSheet,
  formatted: FormattedSheet,
  row: number,
  column: number,
  locale: string,
): string {
  const spec = sheet.columns[column];
  if (!spec) return "";
  if (row === 1) return spec.header;
  const formula = cellFormula(sheet, row, column);
  if (formula) return formula;
  if (row === sheet.row_count + 2 && formatted.totals) return formatted.totals[column] ?? "";
  const value = sheet.rows[row - 2]?.[column] ?? null;
  if (typeof value !== "number") return formatted.rows[row - 2]?.[column] ?? "";
  const raw = new Intl.NumberFormat(locale, { useGrouping: false, maximumSignificantDigits: 15 });
  return spec.type === "percent" ? `${raw.format(value * 100)}%` : raw.format(value);
}

/** An A1 reference found in a formula: its text span and the cells it covers. */
export interface FormulaReference {
  start: number;
  end: number;
  /** Sheet named before "!", or null for the formula's own sheet. */
  sheet: string | null;
  /** Excel rows (1-based) and column indexes (0-based); whole columns or rows run to Infinity. */
  top: number;
  bottom: number;
  left: number;
  right: number;
}

// A cell or cell range, a whole-column range, or a whole-row range; "$" anchors allowed.
const A1 =
  /(?:\$?([A-Za-z]{1,3})\$?(\d+)(?::\$?([A-Za-z]{1,3})\$?(\d+))?|\$?([A-Za-z]{1,3}):\$?([A-Za-z]{1,3})|\$?(\d+):\$?(\d+))(?![\p{L}\p{N}_.(!])/uy;
const NAME = /[\p{L}\p{N}_.]+/uy;
const QUOTED_SHEET = /'((?:[^']|'')+)'!/y;

const columnIndex = (letters: string) =>
  [...letters.toUpperCase()].reduce((index, letter) => index * 26 + letter.charCodeAt(0) - 64, 0) - 1;

function readA1(formula: string, at: number): Omit<FormulaReference, "start" | "sheet"> | null {
  A1.lastIndex = at;
  const m = A1.exec(formula);
  if (!m) return null;
  const end = A1.lastIndex;
  const span = (a: number, b: number) => ({ low: Math.min(a, b), high: Math.max(a, b) });
  if (m[1]) {
    const cols = span(columnIndex(m[1]), columnIndex(m[3] ?? m[1]));
    const rows = span(Number(m[2]), Number(m[4] ?? m[2]));
    return { end, top: rows.low, bottom: rows.high, left: cols.low, right: cols.high };
  }
  if (m[5]) {
    const cols = span(columnIndex(m[5]), columnIndex(m[6]));
    return { end, top: 1, bottom: Infinity, left: cols.low, right: cols.high };
  }
  const rows = span(Number(m[7]), Number(m[8]));
  return { end, top: rows.low, bottom: rows.high, left: 0, right: Infinity };
}

/** The A1 references of a formula, skipping string literals and function or other names. */
export function formulaReferences(formula: string): FormulaReference[] {
  const found: FormulaReference[] = [];
  let i = 0;
  while (i < formula.length) {
    const char = formula[i];
    if (char === '"') {
      const close = formula.indexOf('"', i + 1);
      i = close < 0 ? formula.length : close + 1; // "" escapes re-enter here as an empty literal
      continue;
    }
    let sheet: string | null = null;
    let at = i;
    QUOTED_SHEET.lastIndex = i;
    const quoted = char === "'" ? QUOTED_SHEET.exec(formula) : null;
    if (quoted) {
      sheet = quoted[1].replace(/''/g, "'");
      at = QUOTED_SHEET.lastIndex;
    } else if (char !== "$") {
      NAME.lastIndex = i;
      if (!NAME.exec(formula)) {
        i += 1;
        continue;
      }
      const nameEnd = NAME.lastIndex;
      if (formula[nameEnd] === "!") {
        sheet = formula.slice(i, nameEnd);
        at = nameEnd + 1;
      } else if (!readA1(formula, i)) {
        i = nameEnd; // a function, a named range, a number or TRUE
        continue;
      }
    }
    const ref = readA1(formula, at);
    if (ref) found.push({ start: i, sheet, ...ref });
    i = ref ? ref.end : Math.max(at, i + 1);
  }
  return found;
}
