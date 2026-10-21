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

import { describe, expect, it } from "vitest";
import { columnFormatter, columnLetter, formatSheet, mayClip } from "./spreadsheetFormat";
import type { SpreadsheetColumn } from "./types";

const plain = (value: string) => value.replace(/[\u00a0\u202f]/g, " ");
const cell = (column: SpreadsheetColumn, locale: string) => columnFormatter(column, locale).cell;
const total = (column: SpreadsheetColumn, locale: string) => columnFormatter(column, locale).total;

describe("spreadsheetFormat", () => {
  it("keeps the decimals and the currency of the column", () => {
    const jpy: SpreadsheetColumn = { header: "A", type: "currency", currency: "JPY", decimals: 0 };
    const usd: SpreadsheetColumn = { header: "B", type: "currency", currency: "USD", decimals: 2 };
    expect(plain(cell(jpy, "en")(1200))).toBe("¥1,200");
    expect(plain(cell(usd, "fr")(1300.25))).toBe("1 300,25 $US");
  });

  it("formats a total by its kind", () => {
    const qty: SpreadsheetColumn = { header: "Q", type: "integer", decimals: 0, total: "average" };
    const count: SpreadsheetColumn = { header: "C", type: "percent", decimals: 1, total: "count" };
    expect(total(qty, "en")(1.5)).toBe("1.50");
    expect(total(count, "en")(3)).toBe("3");
    expect(total({ header: "L", type: "text" }, "en")("Total")).toBe("Total");
  });

  it("leaves empty cells and unparsable dates as they are", () => {
    expect(cell({ header: "N", type: "number", decimals: 2 }, "en")(null)).toBe("");
    expect(cell({ header: "D", type: "date" }, "en")("soon")).toBe("soon");
  });

  it("names columns with Excel letters", () => {
    expect([0, 25, 26, 51, 701, 702].map(columnLetter)).toEqual(["A", "Z", "AA", "AZ", "ZZ", "AAA"]);
  });

  it("builds one Intl formatter per column, not per cell", () => {
    const original = Intl.NumberFormat;
    let built = 0;
    const counting = function (...args: ConstructorParameters<typeof Intl.NumberFormat>) {
      built += 1;
      return new original(...args);
    } as unknown as typeof Intl.NumberFormat;
    Intl.NumberFormat = counting;
    try {
      formatSheet(
        {
          name: "S",
          columns: [{ header: "N", type: "number", decimals: 2, total: "sum" }],
          rows: Array.from({ length: 200 }, (_, i) => [i]),
          row_count: 200,
          totals: [19900],
        },
        "en",
      );
    } finally {
      Intl.NumberFormat = original;
    }
    expect(built).toBe(1);
  });

  it("sizes columns like the workbook writer and wraps only long text", () => {
    const { layouts, rows } = formatSheet(
      {
        name: "S",
        columns: [
          { header: "Id", type: "integer", decimals: 0 },
          { header: "Label", type: "text" },
          { header: "Notes", type: "text" },
        ],
        rows: [[1, "Rent", "x".repeat(80)]],
        row_count: 1,
        totals: null,
      },
      "en",
    );
    expect(rows).toEqual([["1", "Rent", "x".repeat(80)]]);
    expect(layouts).toEqual([
      { width: 6, wrap: false },
      { width: 7, wrap: false },
      { width: 60, wrap: true },
    ]);
  });

  it("flags text near its column width as possibly clipped, never wrapped text", () => {
    expect(mayClip("Rent", { width: 6, wrap: false })).toBe(true);
    expect(mayClip("1", { width: 10, wrap: false })).toBe(false);
    expect(mayClip("x".repeat(80), { width: 60, wrap: true })).toBe(false);
    expect(mayClip("", { width: 2, wrap: false })).toBe(false);
  });
});
