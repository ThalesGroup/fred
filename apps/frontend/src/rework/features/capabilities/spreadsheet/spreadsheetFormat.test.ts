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
import {
  cellFormula,
  columnFormatter,
  columnLetter,
  formatSheet,
  formulaBarText,
  formulaReferences,
  mayClip,
} from "./spreadsheetFormat";
import type { SpreadsheetColumn, SpreadsheetSheet } from "./types";

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

  it("gives the formula bar a cell's formula, or its value unformatted like Excel", () => {
    const sheet: SpreadsheetSheet = {
      name: "S",
      columns: [
        {
          header: "Amount",
          type: "currency",
          currency: "EUR",
          decimals: 2,
          total: "sum",
          total_formula: "=SUM(A2:A3)",
        },
        { header: "Rate", type: "percent", decimals: 0 },
        { header: "Due", type: "date" },
        { header: "Diff", type: "number", decimals: 2, formula: "=A{row}-1" },
      ],
      rows: [
        [1234.5, 0.07, "2026-01-31", 1233.5],
        [null, null, null, null],
      ],
      row_count: 2,
      totals: [1234.5, null, null, null],
    };
    const bar = (row: number, column: number, locale = "en") =>
      formulaBarText(sheet, formatSheet(sheet, locale), row, column, locale);
    expect(bar(1, 0)).toBe("Amount");
    expect(bar(2, 0)).toBe("1234.5");
    expect(bar(2, 0, "fr")).toBe("1234,5");
    expect(bar(2, 1)).toBe("7%");
    expect(bar(2, 2)).toBe("01/31/2026");
    expect(bar(3, 3)).toBe("=A3-1");
    expect(bar(3, 0)).toBe("");
    expect(bar(4, 0)).toBe("=SUM(A2:A3)");
    expect(bar(4, 1)).toBe("");
  });

  it("shows a cell's own formula and keeps error values as Excel shows them", () => {
    const sheet: SpreadsheetSheet = {
      name: "Synthèse",
      columns: [
        { header: "Label", type: "text" },
        { header: "Value", type: "number", decimals: 2 },
      ],
      rows: [
        ["CA", 6.5],
        ["Ratio", "#DIV/0!"],
      ],
      row_count: 2,
      totals: null,
      cell_formulas: { B2: "=SUM(Commandes!E2:E3)", B3: "=B2/0" },
    };
    const formatted = formatSheet(sheet, "en");
    expect(formulaBarText(sheet, formatted, 2, 1, "en")).toBe("=SUM(Commandes!E2:E3)");
    expect(formulaBarText(sheet, formatted, 3, 1, "en")).toBe("=B2/0");
    expect(formulaBarText(sheet, formatted, 2, 0, "en")).toBe("CA");
    expect(formatted.rows[1][1]).toBe("#DIV/0!");
  });

  describe("formulaReferences", () => {
    // Each reference as [text, sheet, top, bottom, left, right].
    const refs = (formula: string) =>
      formulaReferences(formula).map((ref) => [
        formula.slice(ref.start, ref.end),
        ref.sheet,
        ref.top,
        ref.bottom,
        ref.left,
        ref.right,
      ]);

    it("finds cells and ranges inside function calls, ignoring $ anchors", () => {
      expect(refs("=SUM(B2:B7)/$A$1")).toEqual([
        ["B2:B7", null, 2, 7, 1, 1],
        ["$A$1", null, 1, 1, 0, 0],
      ]);
      expect(refs("=AVERAGE(C$3:$A2)")).toEqual([["C$3:$A2", null, 2, 3, 0, 2]]);
      expect(refs("=AA10*2")).toEqual([["AA10", null, 10, 10, 26, 26]]);
    });

    it("reads whole columns and whole rows", () => {
      expect(refs("=SUM(B:B)+SUM($2:3)")).toEqual([
        ["B:B", null, 1, Infinity, 1, 1],
        ["$2:3", null, 2, 3, 0, Infinity],
      ]);
    });

    it("keeps the sheet of qualified references, quoted or not", () => {
      expect(refs("='Synthèse'!B4+Data!C2:C3+'It''s'!A1")).toEqual([
        ["'Synthèse'!B4", "Synthèse", 4, 4, 1, 1],
        ["Data!C2:C3", "Data", 2, 3, 2, 2],
        ["'It''s'!A1", "It's", 1, 1, 0, 0],
      ]);
    });

    it("skips string literals, function names and plain numbers", () => {
      expect(refs('=IF(A2="B2",LOG10(C3),"say ""D4""")')).toEqual([
        ["A2", null, 2, 2, 0, 0],
        ["C3", null, 3, 3, 2, 2],
      ]);
      expect(refs("=ROUND(1.5,2)+TRUE")).toEqual([]);
      expect(refs("Total")).toEqual([]);
    });
  });

  it("gives the formula of computed, own-formula and totals cells only", () => {
    const sheet: SpreadsheetSheet = {
      name: "S",
      columns: [
        { header: "A", type: "number", decimals: 0, total_formula: "=SUM(A2:A3)" },
        { header: "B", type: "number", decimals: 0, formula: "=A{row}*2" },
      ],
      rows: [
        [1, 2],
        [3, 6],
      ],
      row_count: 2,
      totals: [4, null],
      cell_formulas: { A3: "=A2+2" },
    };
    expect(cellFormula(sheet, 1, 1)).toBeNull();
    expect(cellFormula(sheet, 2, 0)).toBeNull();
    expect(cellFormula(sheet, 3, 0)).toBe("=A2+2");
    expect(cellFormula(sheet, 3, 1)).toBe("=A3*2");
    expect(cellFormula(sheet, 4, 0)).toBe("=SUM(A2:A3)");
    expect(cellFormula(sheet, 4, 1)).toBeNull();
  });
});
