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

import type { SpreadsheetCell, SpreadsheetColumn } from "./types";

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Numbers and dates align right, like in Excel. */
export function isRightAligned(column: SpreadsheetColumn): boolean {
  return column.type !== "text";
}

function formatNumber(value: number, locale: string, column: SpreadsheetColumn, decimals: number): string {
  const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
  if (column.type === "percent") return new Intl.NumberFormat(locale, { ...digits, style: "percent" }).format(value);
  if (column.type === "currency" && column.currency) {
    return new Intl.NumberFormat(locale, { ...digits, style: "currency", currency: column.currency }).format(value);
  }
  return new Intl.NumberFormat(locale, digits).format(value);
}

function formatDate(value: string, locale: string): string {
  const match = ISO_DATE.exec(value);
  if (!match) return value;
  const utc = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return new Intl.DateTimeFormat(locale, { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit" }).format(
    utc,
  );
}

export function formatCell(value: SpreadsheetCell, column: SpreadsheetColumn, locale: string): string {
  if (value === null || value === undefined) return "";
  if (column.type === "date" && typeof value === "string") return formatDate(value, locale);
  if (typeof value !== "number") return String(value);
  return formatNumber(value, locale, column, column.decimals ?? 0);
}

/** A total keeps its column's format, except a count (whole) and an integer average. */
export function formatTotal(value: SpreadsheetCell, column: SpreadsheetColumn, locale: string): string {
  if (typeof value !== "number") return value ?? "";
  if (column.total === "count") return new Intl.NumberFormat(locale).format(value);
  if (column.total === "average" && column.type === "integer") return formatNumber(value, locale, column, 2);
  return formatCell(value, column, locale);
}
