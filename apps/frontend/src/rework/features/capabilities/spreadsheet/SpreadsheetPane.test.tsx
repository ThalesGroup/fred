// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SpreadsheetPreview, SpreadsheetPreviewPartData } from "./types";
import type { SpreadsheetPreviewLoad } from "./useSpreadsheetPreview";

const state = vi.hoisted(() => ({
  current: null as SpreadsheetPreviewPartData | null,
  load: { status: "loading" } as SpreadsheetPreviewLoad,
  language: "en",
}));

vi.mock("./useSpreadsheetPreview", () => ({
  useSessionSpreadsheet: () => state.current,
  useSpreadsheetPreview: () => state.load,
}));
vi.mock("./SpreadsheetDownloadButton", () => ({
  default: () => <button type="button">download</button>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { formatted?: string }) => (options?.formatted ? `${key}:${options.formatted}` : key),
    i18n: { language: state.language },
  }),
}));

const { SpreadsheetPane } = await import("./SpreadsheetPane");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

const part: SpreadsheetPreviewPartData = {
  type: "spreadsheet_preview",
  preview_id: "teams/t/q3.xlsx",
  title: "Q3 budget.xlsx",
  file_name: "Q3 budget.xlsx",
  xlsx_download_url: "/fs/download/q3.xlsx",
  preview_url: "/fs/download/q3.preview.json",
};

const preview: SpreadsheetPreview = {
  version: 1,
  sheets: [
    {
      name: "Budget",
      columns: [
        { header: "Line", type: "text" },
        { header: "Amount", type: "currency", currency: "EUR", decimals: 2, total: "sum" },
        { header: "Rate", type: "percent", decimals: 1 },
        { header: "Due", type: "date" },
      ],
      rows: [
        ["Rent", 1200, 0.125, "2026-01-31"],
        ["Travel", 350.5, null, null],
      ],
      row_count: 2,
      totals: ["Total", 1550.5, null, null],
    },
    {
      name: "Detail",
      columns: [{ header: "Qty", type: "integer", decimals: 0 }],
      rows: [[3]],
      row_count: 1520,
      totals: null,
    },
  ],
};

// Intl separates groups and currency symbols with (narrow) no-break spaces.
const text = (el: Element | null | undefined) => (el?.textContent ?? "").replace(/[  ]/g, " ");

async function render() {
  await act(async () => root.render(<SpreadsheetPane capabilityId="spreadsheet" onClose={() => undefined} />));
}

beforeEach(() => {
  state.current = part;
  state.load = { status: "ready", preview };
  state.language = "en";
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("SpreadsheetPane", () => {
  it("shows the file name, the download button and one tab per sheet", async () => {
    await render();
    expect(container.textContent).toContain("Q3 budget.xlsx");
    expect(container.textContent).toContain("download");
    const tabs = [...container.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent);
    expect(tabs).toEqual(["Budget", "Detail"]);
  });

  it("formats currency, percent and dates in the user's locale and aligns numbers right", async () => {
    await render();
    const cells = [...container.querySelectorAll("tbody tr:first-child td")];
    expect(cells.map(text)).toEqual(["Rent", "€1,200.00", "12.5%", "01/31/2026"]);
    expect(cells[0].className).toBe("");
    expect(cells[1].className).not.toBe("");

    await act(async () => root.unmount());
    root = createRoot(container);
    state.language = "fr";
    await render();
    const fr = [...container.querySelectorAll("tbody tr:first-child td")].map(text);
    expect(fr).toEqual(["Rent", "1 200,00 €", "12,5 %", "31/01/2026"]);
  });

  it("renders the totals row in the table footer", async () => {
    await render();
    const totals = [...container.querySelectorAll("tfoot td")].map(text);
    expect(totals).toEqual(["Total", "€1,550.50", "", ""]);
  });

  it("switches sheet and says how many rows the preview leaves out", async () => {
    await render();
    expect(container.textContent).not.toContain("capability.spreadsheet.moreRows");
    const detail = [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')][1];
    await act(async () => detail.click());
    expect(text(container.querySelector("tbody td"))).toBe("3");
    expect(container.querySelector("tfoot")).toBeNull();
    expect(text(container)).toContain("capability.spreadsheet.moreRows:1,519");
  });

  it("shows no tabs for a single sheet", async () => {
    state.load = { status: "ready", preview: { ...preview, sheets: [preview.sheets[0]] } };
    await render();
    expect(container.querySelector('[role="tab"]')).toBeNull();
  });

  it("falls back to an unavailable message when the preview cannot load", async () => {
    state.load = { status: "error" };
    await render();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("capability.spreadsheet.unavailable");
    expect(container.querySelector("table")).toBeNull();
    expect(container.textContent).toContain("download");
  });

  it("says there is nothing to preview without a spreadsheet in the conversation", async () => {
    state.current = null;
    await render();
    expect(container.textContent).toContain("capability.spreadsheet.empty");
  });
});
