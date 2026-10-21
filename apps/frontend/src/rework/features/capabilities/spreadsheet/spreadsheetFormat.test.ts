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
import { formatCell, formatTotal } from "./spreadsheetFormat";
import type { SpreadsheetColumn } from "./types";

const plain = (value: string) => value.replace(/[  ]/g, " ");

describe("spreadsheetFormat", () => {
  it("keeps the decimals and the currency of the column", () => {
    const jpy: SpreadsheetColumn = { header: "A", type: "currency", currency: "JPY", decimals: 0 };
    const usd: SpreadsheetColumn = { header: "B", type: "currency", currency: "USD", decimals: 2 };
    expect(plain(formatCell(1200, jpy, "en"))).toBe("¥1,200");
    expect(plain(formatCell(1300.25, usd, "fr"))).toBe("1 300,25 $US");
  });

  it("formats a total by its kind", () => {
    const qty: SpreadsheetColumn = { header: "Q", type: "integer", decimals: 0, total: "average" };
    const count: SpreadsheetColumn = { header: "C", type: "percent", decimals: 1, total: "count" };
    expect(formatTotal(1.5, qty, "en")).toBe("1.50");
    expect(formatTotal(3, count, "en")).toBe("3");
    expect(formatTotal("Total", { header: "L", type: "text" }, "en")).toBe("Total");
  });

  it("leaves empty cells and unparsable dates as they are", () => {
    expect(formatCell(null, { header: "N", type: "number", decimals: 2 }, "en")).toBe("");
    expect(formatCell("soon", { header: "D", type: "date" }, "en")).toBe("soon");
  });
});
