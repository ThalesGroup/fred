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
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import DataTable, { DataTableColumn, SortState } from "./DataTable.tsx";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

interface Row {
  id: number;
}

const columns: DataTableColumn<Row>[] = [{ label: "Id", cellRenderer: (row) => <span>{row.id}</span> }];

function makeRows(count: number): Row[] {
  return Array.from({ length: count }, (_, i) => ({ id: i + 1 }));
}

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function rowValues(): string[] {
  return Array.from(container.querySelectorAll('[class*="datatable-row"] span')).map((el) => el.textContent ?? "");
}

function footer(): Element | null {
  return container.querySelector('[class*="datatable-footer"]');
}

/** [rowsPerPageSelect, firstPage, prevPage, nextPage, lastPage] */
function footerButtons(): HTMLButtonElement[] {
  return Array.from(footer()?.querySelectorAll("button") ?? []);
}

describe("DataTable", () => {
  it("renders every row with no footer when pageSize is omitted", () => {
    render(<DataTable columns={columns} data={makeRows(45)} />);
    expect(rowValues()).toHaveLength(45);
    expect(footer()).toBeNull();
  });

  // Regression: the header used to live inside the same scrolling grid as
  // the rows (pinned on top via `position: sticky`), so the scrollbar track
  // spanned the header's own height too. The header is now a structurally
  // separate grid, sibling to the scrollable row grid, so the header cell
  // is never a descendant of the scrolling container.
  it("keeps the header structurally outside the scrollable row container", () => {
    render(<DataTable columns={columns} data={makeRows(5)} />);
    const header = container.querySelector('[class*="datatable-header"]');
    const body = container.querySelector('[class*="datatable-body"]');
    expect(header).not.toBeNull();
    expect(body).not.toBeNull();
    expect(body?.contains(header!)).toBe(false);
    expect(header?.textContent).toBe("Id");
  });

  // Regression: two columns with the same (often empty, e.g. an unlabeled
  // status/actions cell) label used to collide on `key={column.label}` for
  // both header and body cells, which broke reconciliation badly enough to
  // stop the page from rendering at all in production.
  it("does not warn about duplicate keys when multiple columns share an (empty) label", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const multiBlankColumns: DataTableColumn<Row>[] = [
      { label: "Id", cellRenderer: (row) => <span>{row.id}</span> },
      { label: "", cellRenderer: () => <span>status</span> },
      { label: "", cellRenderer: () => <span>actions</span> },
    ];

    render(<DataTable columns={multiBlankColumns} data={makeRows(3)} />);

    const duplicateKeyWarning = consoleError.mock.calls.some((call) => String(call[0]).includes("same key"));
    expect(duplicateKeyWarning).toBe(false);
    consoleError.mockRestore();
  });

  it("threads a custom rowHeight into the container as a CSS variable, leaving other consumers' default untouched", () => {
    render(<DataTable columns={columns} data={makeRows(3)} rowHeight="2.5rem" />);
    const container = document.querySelector('[class*="datatable-container"]') as HTMLElement;
    expect(container.style.getPropertyValue("--datatable-row-height")).toBe("2.5rem");
  });

  it("maps the size preset to its row-height CSS variable", () => {
    render(<DataTable columns={columns} data={makeRows(3)} size="medium" />);
    const mediumContainer = document.querySelector('[class*="datatable-container"]') as HTMLElement;
    expect(mediumContainer.style.getPropertyValue("--datatable-row-height")).toBe("3rem");
  });

  it("lets an explicit rowHeight override the size preset", () => {
    render(<DataTable columns={columns} data={makeRows(3)} size="medium" rowHeight="4rem" />);
    const container = document.querySelector('[class*="datatable-container"]') as HTMLElement;
    expect(container.style.getPropertyValue("--datatable-row-height")).toBe("4rem");
  });

  it("shows a persistent footer with the total item count even when every row fits on one page", () => {
    render(<DataTable columns={columns} data={makeRows(10)} pageSize={20} />);
    expect(rowValues()).toHaveLength(10);
    const [, first, prev, next, last] = footerButtons();
    expect(footer()?.textContent).toContain("10");
    expect(first.hasAttribute("disabled")).toBe(true);
    expect(prev.hasAttribute("disabled")).toBe(true);
    expect(next.hasAttribute("disabled")).toBe(true);
    expect(last.hasAttribute("disabled")).toBe(true);
  });

  it("shows only the first page's rows, the current page number, and the total count", () => {
    render(<DataTable columns={columns} data={makeRows(45)} pageSize={20} />);
    expect(rowValues()).toEqual(makeRows(20).map((r) => String(r.id)));
    expect(footer()?.textContent).toContain("45");
    expect(footer()?.textContent).toContain("1");
  });

  it("navigates next/prev/first/last, disabling the relevant buttons at each end", () => {
    render(<DataTable columns={columns} data={makeRows(45)} pageSize={20} />);
    const [, first, prev, next, last] = footerButtons();
    expect(first.hasAttribute("disabled")).toBe(true);
    expect(prev.hasAttribute("disabled")).toBe(true);
    expect(next.hasAttribute("disabled")).toBe(false);
    expect(last.hasAttribute("disabled")).toBe(false);

    click(next);
    expect(rowValues()[0]).toBe("21");
    expect(rowValues()).toHaveLength(20);
    expect(first.hasAttribute("disabled")).toBe(false);
    expect(prev.hasAttribute("disabled")).toBe(false);

    click(last);
    expect(rowValues()).toEqual(["41", "42", "43", "44", "45"]);
    expect(next.hasAttribute("disabled")).toBe(true);
    expect(last.hasAttribute("disabled")).toBe(true);

    click(first);
    expect(rowValues()[0]).toBe("1");
    expect(prev.hasAttribute("disabled")).toBe(true);
  });
});

describe("DataTable sorting", () => {
  const sortableColumns: DataTableColumn<Row>[] = [
    { label: "Id", cellRenderer: (row) => <span>{row.id}</span>, sortable: true, sortValue: (row) => row.id },
  ];

  function headerButton(): HTMLButtonElement {
    return container.querySelector('[class*="header-sort-button"]') as HTMLButtonElement;
  }

  it("sorts ascending then descending then back to the original order (uncontrolled)", () => {
    const rows = [{ id: 3 }, { id: 1 }, { id: 2 }];
    render(<DataTable columns={sortableColumns} data={rows} />);
    expect(rowValues()).toEqual(["3", "1", "2"]);

    click(headerButton());
    expect(rowValues()).toEqual(["1", "2", "3"]);

    click(headerButton());
    expect(rowValues()).toEqual(["3", "2", "1"]);

    click(headerButton());
    expect(rowValues()).toEqual(["3", "1", "2"]);
  });

  it("defers to the caller in controlled mode instead of sorting locally", () => {
    const rows = [{ id: 3 }, { id: 1 }, { id: 2 }];
    const onSortChange = vi.fn();
    render(<DataTable columns={sortableColumns} data={rows} sortState={null} onSortChange={onSortChange} />);

    click(headerButton());

    // Data order is untouched — the caller owns re-fetching/re-sorting.
    expect(rowValues()).toEqual(["3", "1", "2"]);
    expect(onSortChange).toHaveBeenCalledWith({ columnLabel: "Id", direction: "asc" });
  });

  it("reflects the controlled sortState's direction on the active column", () => {
    const rows = [{ id: 3 }, { id: 1 }, { id: 2 }];
    const sortState: SortState = { columnLabel: "Id", direction: "desc" };
    render(<DataTable columns={sortableColumns} data={rows} sortState={sortState} onSortChange={vi.fn()} />);

    expect(headerButton().dataset.active).toBe("true");
  });
});

describe("DataTable selection", () => {
  const rows = makeRows(3);

  function checkboxes(): HTMLInputElement[] {
    return Array.from(container.querySelectorAll('input[type="checkbox"]'));
  }

  it("renders one checkbox per row plus a header checkbox", () => {
    render(<DataTable columns={columns} data={rows} selectable rowKey={(r) => r.id} selectedKeys={new Set()} />);
    expect(checkboxes()).toHaveLength(4);
  });

  it("toggles a single row and reports the updated selection", () => {
    const onSelectionChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set([1])}
        onSelectionChange={onSelectionChange}
      />,
    );

    // checkboxes()[0] is the header "select all"; row checkboxes follow in row order.
    click(checkboxes()[2]);

    expect(onSelectionChange).toHaveBeenCalledWith(new Set([1, 2]));
  });

  it("selects/deselects every row on the page via the header checkbox", () => {
    const onSelectionChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set()}
        onSelectionChange={onSelectionChange}
      />,
    );

    click(checkboxes()[0]);
    expect(onSelectionChange).toHaveBeenCalledWith(new Set([1, 2, 3]));
  });

  function rowElements(): HTMLElement[] {
    return Array.from(container.querySelectorAll('[class*="datatable-row"]'));
  }

  it("marks a selected row's cells with data-selected, for the primary-tint background", () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set([2])}
        onSelectionChange={vi.fn()}
      />,
    );

    expect(rowElements().map((row) => row.hasAttribute("data-selected"))).toEqual([false, true, false]);
  });

  it("toggles the row when clicking its background, not just its checkbox", () => {
    const onSelectionChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set()}
        onSelectionChange={onSelectionChange}
      />,
    );

    // A cell's own content (a plain <span>, no interactive element) counts
    // as "the row's background" for this purpose.
    click(container.querySelector('[class*="datatable-row"] span'));

    expect(onSelectionChange).toHaveBeenCalledWith(new Set([1]));
  });

  it("does not double-toggle when the click lands on the checkbox itself", () => {
    const onSelectionChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set()}
        onSelectionChange={onSelectionChange}
      />,
    );

    click(checkboxes()[1]);

    expect(onSelectionChange).toHaveBeenCalledTimes(1);
    expect(onSelectionChange).toHaveBeenCalledWith(new Set([1]));
  });

  // Regression: Checkbox's native <input> is visually hidden and wrapped in
  // a <label> (Checkbox.tsx) — a real click lands on that label (or its
  // visible box), not the input directly, and the browser then separately
  // forwards a synthetic click to the input. The row's own click-to-select
  // handler used to only exclude `input`, so it fired on the first (label)
  // click while the checkbox's onChange fired on the forwarded one — two
  // toggles cancelling out, so clicking the checkbox appeared to do nothing.
  it("toggles exactly once when the click lands on the checkbox's label, not the input", () => {
    const onSelectionChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set()}
        onSelectionChange={onSelectionChange}
      />,
    );

    // Clicking the label natively forwards a click to its associated input
    // (real browser behavior, also reproduced here) — the row handler must
    // not ALSO toggle from the original label click, or the two cancel out.
    const label = checkboxes()[1].closest("label");
    click(label);

    expect(onSelectionChange).toHaveBeenCalledTimes(1);
    expect(onSelectionChange).toHaveBeenCalledWith(new Set([1]));
  });

  it("does not toggle selection when the click lands on a button inside a cell", () => {
    const onSelectionChange = vi.fn();
    const onButtonClick = vi.fn();
    const columnsWithButton: DataTableColumn<Row>[] = [
      {
        label: "Id",
        cellRenderer: (row) => (
          <button type="button" onClick={onButtonClick}>
            {row.id}
          </button>
        ),
      },
    ];
    render(
      <DataTable
        columns={columnsWithButton}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set()}
        onSelectionChange={onSelectionChange}
      />,
    );

    click(container.querySelector('[class*="datatable-row"] button'));

    expect(onButtonClick).toHaveBeenCalledTimes(1);
    expect(onSelectionChange).not.toHaveBeenCalled();
  });

  it("marks the header checkbox indeterminate when only some rows are selected", () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set([1])}
        onSelectionChange={vi.fn()}
      />,
    );

    expect(checkboxes()[0].hasAttribute("data-indeterminate")).toBe(true);
  });

  // Regression: the checkbox cell used to be a plain `.datatable-cell`, so
  // `firstColumnInset`'s `:first-child` rule (meant for the Name/label
  // column) landed on the checkbox instead, shoving it off-center in its
  // narrow track. The checkbox cell now carries its own class so the CSS
  // can target it (center it) and exclude it from that inset independently.
  it("gives the checkbox cell its own class, distinct from a plain content cell", () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        selectable
        rowKey={(r) => r.id}
        selectedKeys={new Set()}
        onSelectionChange={vi.fn()}
      />,
    );

    const checkboxCell = checkboxes()[0].closest('[class*="datatable-cell"]');
    expect(checkboxCell?.className).toMatch(/datatable-cell-select/);
  });
});

describe("DataTable server pagination", () => {
  // `data` here is already "the current page" (as a real caller would fetch
  // it) — never a full dataset DataTable would need to slice itself.
  const currentPageRows = makeRows(3);

  it("shows the caller's totalCount, not data.length, and renders every row passed without re-slicing", () => {
    render(
      <DataTable
        columns={columns}
        data={currentPageRows}
        serverPagination={{ totalCount: 120, offset: 20, limit: 10, onOffsetChange: vi.fn() }}
      />,
    );
    expect(footer()?.textContent).toContain("120");
    expect(rowValues()).toEqual(currentPageRows.map((r) => String(r.id)));
  });

  it("derives the current/total page count from totalCount and limit, and calls onOffsetChange on navigation", () => {
    const onOffsetChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={currentPageRows}
        serverPagination={{ totalCount: 100, offset: 20, limit: 10, onOffsetChange, onLimitChange: vi.fn() }}
      />,
    );
    // offset 20 / limit 10 -> page 3 of 10
    expect(footer()?.textContent).toContain("3");
    expect(footer()?.textContent).toContain("10");

    const [, first, prev, next, last] = footerButtons();
    click(next);
    expect(onOffsetChange).toHaveBeenCalledWith(30);
    click(prev);
    expect(onOffsetChange).toHaveBeenCalledWith(10);
    click(first);
    expect(onOffsetChange).toHaveBeenCalledWith(0);
    click(last);
    expect(onOffsetChange).toHaveBeenCalledWith(90);
  });

  it("hides the rows-per-page selector when onLimitChange is omitted", () => {
    render(
      <DataTable
        columns={columns}
        data={currentPageRows}
        serverPagination={{ totalCount: 100, offset: 0, limit: 10, onOffsetChange: vi.fn() }}
      />,
    );
    expect(footer()?.textContent).not.toContain("dataTable.pagination.itemsPerPage");
    // Only the 4 nav buttons remain, no rows-per-page select control.
    expect(footerButtons()).toHaveLength(4);
  });

  it("shows the rows-per-page selector when onLimitChange is provided", () => {
    render(
      <DataTable
        columns={columns}
        data={currentPageRows}
        serverPagination={{ totalCount: 100, offset: 0, limit: 10, onOffsetChange: vi.fn(), onLimitChange: vi.fn() }}
      />,
    );
    expect(footer()?.textContent).toContain("dataTable.pagination.itemsPerPage");
    expect(footerButtons()).toHaveLength(5);
  });

  it("disables first/prev on the first page and next/last on the last page", () => {
    render(
      <DataTable
        columns={columns}
        data={currentPageRows}
        serverPagination={{ totalCount: 30, offset: 0, limit: 10, onOffsetChange: vi.fn(), onLimitChange: vi.fn() }}
      />,
    );
    const [, first, prev, next, last] = footerButtons();
    expect(first.hasAttribute("disabled")).toBe(true);
    expect(prev.hasAttribute("disabled")).toBe(true);
    expect(next.hasAttribute("disabled")).toBe(false);
    expect(last.hasAttribute("disabled")).toBe(false);
  });

  it("clamps offset back to the last valid page once totalCount drops below it (e.g. deleting every row on a later page)", () => {
    const onOffsetChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={[]}
        serverPagination={{ totalCount: 5, offset: 20, limit: 10, onOffsetChange }}
      />,
    );
    expect(onOffsetChange).toHaveBeenCalledWith(0);
  });

  it("does not touch the offset while it is still within range", () => {
    const onOffsetChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        data={currentPageRows}
        serverPagination={{ totalCount: 100, offset: 20, limit: 10, onOffsetChange }}
      />,
    );
    expect(onOffsetChange).not.toHaveBeenCalled();
  });
});
