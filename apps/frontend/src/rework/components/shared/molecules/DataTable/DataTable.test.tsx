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
});
