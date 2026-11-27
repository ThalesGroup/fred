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
    t: (key: string, options?: { formatted?: string; date?: string }) =>
      options?.formatted || options?.date ? `${key}:${options.formatted ?? options.date}` : key,
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
const text = (el: Element | null | undefined) => (el?.textContent ?? "").replace(/[\u00a0\u202f]/g, " ");

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

const cells = (selector: string) => [...container.querySelectorAll(selector)].map(text);
// The formula bar: name box, "fx", then the formula or value of the selected cell.
const barText = () => text(container.querySelector("output ~ span:last-child"));

// happy-dom has no layout: fake the tab strip being narrower than its tabs.
function fakeOverflow(clientWidth: number, scrollWidth: number) {
  const owner = (name: string) => {
    let proto: object | null = HTMLElement.prototype;
    while (proto && !Object.getOwnPropertyDescriptor(proto, name)) proto = Object.getPrototypeOf(proto);
    return (proto ?? HTMLElement.prototype) as HTMLElement;
  };
  vi.spyOn(owner("clientWidth"), "clientWidth", "get").mockReturnValue(clientWidth);
  vi.spyOn(owner("scrollWidth"), "scrollWidth", "get").mockReturnValue(scrollWidth);
}

describe("SpreadsheetPane", () => {
  it("shows the file name, the download button and the sheet tabs below the grid", async () => {
    await render();
    expect(container.textContent).toContain("Q3 budget.xlsx");
    expect(container.textContent).toContain("download");
    expect(cells('[role="tab"]')).toEqual(["Budget", "Detail"]);
    const tablist = container.querySelector('[role="tablist"]')!;
    const table = container.querySelector("table")!;
    expect(table.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('[role="tabpanel"]')?.getAttribute("aria-labelledby")).toBe(
      container.querySelector('[role="tab"][aria-selected="true"]')?.id,
    );
  });

  it("frames the grid with column letters and row numbers, the workbook header as row 1", async () => {
    await render();
    expect(cells("thead tr:first-child td")).toEqual(["", "A", "B", "C", "D"]);
    expect(cells('thead th[scope="col"]')).toEqual(["Line", "Amount", "Rate", "Due"]);
    expect(cells('th[scope="row"]')).toEqual(["1", "2", "3", "4"]);
  });

  it("formats currency, percent and dates in the user's locale and aligns numbers right", async () => {
    await render();
    const first = [...container.querySelectorAll("tbody tr:first-child td")];
    expect(first.map(text)).toEqual(["Rent", "€1,200.00", "12.5%", "01/31/2026"]);
    expect(first[0].className).toBe("");
    expect(first[1].className).not.toBe("");

    await act(async () => root.unmount());
    root = createRoot(container);
    state.language = "fr";
    await render();
    expect(cells("tbody tr:first-child td")).toEqual(["Rent", "1 200,00 €", "12,5 %", "31/01/2026"]);
  });

  it("renders the totals row last, with its row number in the file", async () => {
    await render();
    expect(cells("tfoot td")).toEqual(["Total", "€1,550.50", "", ""]);
    expect(cells("tfoot th")).toEqual(["4"]);
  });

  it("shows the address of the clicked cell and its unformatted value in the formula bar", async () => {
    await render();
    expect(cells("output")).toEqual(["A1"]);
    const amount = container.querySelectorAll<HTMLElement>("tbody tr:nth-child(2) td")[1];
    await act(async () => amount.click());
    expect(cells("output")).toEqual(["B3"]);
    expect(barText()).toBe("350.5");
  });

  it("moves the selection with the arrow keys, keeping a single focusable cell", async () => {
    await render();
    const table = container.querySelector("table")!;
    const press = async (key: string) =>
      act(async () => {
        (document.activeElement ?? table).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      });
    expect(container.querySelectorAll('[tabindex="0"][data-cell]')).toHaveLength(1);
    container.querySelector<HTMLElement>('[data-cell="1:0"]')!.focus();

    await press("ArrowDown");
    await press("ArrowRight");
    expect(cells("output")).toEqual(["B2"]);
    expect(document.activeElement?.getAttribute("data-cell")).toBe("2:1");
    expect(barText()).toBe("1200");

    // Down past the last preview row lands on the totals row; edges clamp.
    for (const key of ["ArrowDown", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowLeft"]) await press(key);
    expect(cells("output")).toEqual(["A4"]);
    expect(barText()).toBe("Total");
    const focusable = [...container.querySelectorAll('[tabindex="0"][data-cell]')];
    expect(focusable.map((el) => el.getAttribute("data-cell"))).toEqual(["4:0"]);
  });

  it("scrolls the grid to keep the selected cell clear of the sticky headings", async () => {
    await render();
    const table = container.querySelector("table")!;
    const scroller = table.parentElement!;
    let scrollLeft = 0;
    Object.defineProperty(scroller, "scrollLeft", {
      configurable: true,
      get: () => scrollLeft,
      set: (v) => (scrollLeft = v),
    });
    Object.defineProperty(scroller, "clientWidth", { configurable: true, value: 300 });
    Object.defineProperty(scroller, "clientHeight", { configurable: true, value: 200 });
    // Fake layout: 40px row numbers, 50px of sticky heading rows, 100px columns, 20px rows.
    const rect = (left: number, top: number, width: number, height: number) =>
      ({ left, top, right: left + width, bottom: top + height, width, height }) as DOMRect;
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      if (this === scroller) return rect(0, 0, 300, 200);
      if (this.tagName === "THEAD") return rect(0, 0, 440, 50);
      if (this.getAttribute("scope") === "row") return rect(0, 0, 40, 20);
      const [row, column] = (this.dataset.cell ?? "0:0").split(":").map(Number);
      return rect(40 + column * 100 - scrollLeft, 30 + row * 20, 100, 20);
    });
    try {
      const press = async (key: string) =>
        act(async () => {
          document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
        });
      await act(async () => container.querySelector<HTMLElement>('[data-cell="2:0"]')!.click());
      const seen: number[] = [];
      for (const key of ["ArrowRight", "ArrowRight", "ArrowRight", "ArrowLeft", "ArrowLeft", "ArrowLeft"]) {
        await press(key);
        seen.push(scrollLeft);
      }
      // Right edge followed going right; the sticky row numbers cleared going back left.
      expect(seen).toEqual([0, 40, 140, 140, 100, 0]);
      expect(document.activeElement?.getAttribute("data-cell")).toBe("2:0");
    } finally {
      vi.restoreAllMocks();
    }
  });

  it("shows the formula of computed and totals cells like Excel's formula bar, the value in the cell", async () => {
    state.load = {
      status: "ready",
      preview: {
        version: 1,
        sheets: [
          {
            name: "Budget",
            columns: [
              { header: "Line", type: "text" },
              {
                header: "Budget",
                type: "currency",
                currency: "EUR",
                decimals: 2,
                total: "sum",
                total_formula: "=SUM(B2:B3)",
              },
              { header: "Rate", type: "percent", decimals: 0, formula: '=IFERROR(ROUND(C{row}/B{row},2),"")' },
            ],
            rows: [
              ["Rent", 1200, 0.96],
              [null, 0, null],
            ],
            row_count: 2,
            totals: ["Total", 1200, null],
          },
        ],
      },
    };
    await render();
    const select = async (address: string) =>
      act(async () => container.querySelector<HTMLElement>(`[data-cell="${address}"]`)!.click());

    expect(container.textContent).toContain("fx");
    await select("3:2");
    expect(cells("output")).toEqual(["C3"]);
    expect(barText()).toBe('=IFERROR(ROUND(C3/B3,2),"")');
    expect(text(container.querySelector('[data-cell="3:2"]'))).toBe("");
    await select("2:2");
    expect(barText()).toBe('=IFERROR(ROUND(C2/B2,2),"")');
    expect(text(container.querySelector('[data-cell="2:2"]'))).toBe("96%");
    await select("4:1");
    expect(barText()).toBe("=SUM(B2:B3)");
    expect(text(container.querySelector('[data-cell="4:1"]'))).toBe("€1,200.00");
    // A literal cell shows its value; an empty one stays empty, never "null".
    await select("4:0");
    expect(barText()).toBe("Total");
    await select("3:0");
    expect(barText()).toBe("");
    expect(container.querySelector("tbody")?.textContent).not.toContain("null");

    // Keyboard moves update the bar too.
    for (const key of ["ArrowUp", "ArrowRight", "ArrowRight"]) {
      await act(async () => {
        document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      });
    }
    expect(cells("output")).toEqual(["C2"]);
    expect(barText()).toBe('=IFERROR(ROUND(C2/B2,2),"")');
  });

  it("marks the cells the selected formula references, and none for a plain cell", async () => {
    const [budget, detail] = preview.sheets;
    const columns = budget.columns.map((column, index) =>
      index === 1 ? { ...column, total_formula: "=SUM(B2:B3)+'Detail'!A2" } : column,
    );
    state.load = { status: "ready", preview: { ...preview, sheets: [{ ...budget, columns }, detail] } };
    await render();
    const marked = () =>
      [...container.querySelectorAll('[data-cell][class*="referenced"]')].map((el) => el.getAttribute("data-cell"));
    const total = container.querySelector<HTMLElement>('[data-cell="4:1"]')!;
    await act(async () => total.click());
    expect(barText()).toBe("=SUM(B2:B3)+'Detail'!A2");
    // The other sheet's reference is coloured in the bar but marks nothing in this grid.
    expect(marked()).toEqual(["2:1", "3:1"]);
    expect(cells("output ~ span:last-child [class*='reference']")).toEqual(["B2:B3", "'Detail'!A2"]);
    expect(total.className).not.toMatch(/referenced/);

    await act(async () => container.querySelector<HTMLElement>('[data-cell="2:0"]')!.click());
    expect(marked()).toEqual([]);
    expect(container.querySelector("output ~ span:last-child [class*='reference']")).toBeNull();
  });

  it("gives cells that may be cut a title with their full text", async () => {
    const long = "A fairly long description";
    state.load = {
      status: "ready",
      preview: {
        version: 1,
        sheets: [
          {
            name: "Notes",
            columns: [{ header: "Note", type: "text" }],
            rows: [[long], ["ok"]],
            row_count: 2,
            totals: null,
          },
        ],
      },
    };
    await render();
    const [first, second] = [...container.querySelectorAll("tbody td")];
    expect(first.getAttribute("title")).toBe(long);
    expect(second.hasAttribute("title")).toBe(false);
  });

  it("switches sheet from the bottom tabs, by click or keyboard, and says how many rows are left out", async () => {
    await render();
    expect(container.textContent).not.toContain("capability.spreadsheet.moreRows");
    const [budget, detail] = [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
    await act(async () => detail.click());
    expect(text(container.querySelector("tbody td"))).toBe("3");
    expect(container.querySelector("tfoot")).toBeNull();
    expect(text(container)).toContain("capability.spreadsheet.moreRows:1,519");

    await act(async () => detail.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })));
    expect(budget.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(budget);
    expect(text(container.querySelector("tbody td"))).toBe("Rent");
  });

  it("says when values were computed at build time, only when TODAY or NOW were read", async () => {
    await render();
    expect(container.textContent).not.toContain("capability.spreadsheet.computedOn");
    state.load = { status: "ready", preview: { ...preview, computed_at: "2026-10-28" } };
    state.language = "fr";
    await render();
    expect(text(container)).toContain("capability.spreadsheet.computedOn:28/10/2026");
  });

  it("keeps one tab for a single sheet and no scroll arrows when the tabs fit", async () => {
    state.load = { status: "ready", preview: { ...preview, sheets: [preview.sheets[0]] } };
    await render();
    expect(cells('[role="tab"]')).toEqual(["Budget"]);
    expect(container.querySelector('[aria-label="capability.spreadsheet.nextSheets"]')).toBeNull();
  });

  it("shows tab scroll arrows, disabled at the ends, when the tabs overflow", async () => {
    fakeOverflow(100, 300);
    try {
      await render();
      const prev = container.querySelector<HTMLButtonElement>('[aria-label="capability.spreadsheet.previousSheets"]')!;
      const next = container.querySelector<HTMLButtonElement>('[aria-label="capability.spreadsheet.nextSheets"]')!;
      expect(prev.disabled).toBe(true);
      expect(next.disabled).toBe(false);

      const list = container.querySelector<HTMLElement>('[role="tablist"]')!;
      const scrollBy = vi.fn();
      list.scrollBy = scrollBy;
      await act(async () => next.click());
      expect(scrollBy).toHaveBeenCalledWith(expect.objectContaining({ left: 60 }));

      Object.defineProperty(list, "scrollLeft", { configurable: true, value: 200 });
      await act(async () => list.dispatchEvent(new Event("scroll")));
      expect(prev.disabled).toBe(false);
      expect(next.disabled).toBe(true);
    } finally {
      vi.restoreAllMocks();
    }
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
