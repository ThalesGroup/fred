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
import DataTable, { DataTableColumn } from "./DataTable.tsx";

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

describe("DataTable", () => {
  it("renders every row with no footer when pageSize is omitted", () => {
    render(<DataTable columns={columns} data={makeRows(45)} />);
    expect(rowValues()).toHaveLength(45);
    expect(container.querySelector('[class*="datatable-footer"]')).toBeNull();
  });

  it("hides the pagination footer when every row fits on one page", () => {
    render(<DataTable columns={columns} data={makeRows(10)} pageSize={20} />);
    expect(rowValues()).toHaveLength(10);
    expect(container.querySelector('[class*="datatable-footer"]')).toBeNull();
  });

  it("shows only the first page's rows and a footer when data exceeds pageSize", () => {
    render(<DataTable columns={columns} data={makeRows(45)} pageSize={20} />);
    expect(rowValues()).toEqual(makeRows(20).map((r) => String(r.id)));
    const footer = container.querySelector('[class*="datatable-footer"]');
    expect(footer).not.toBeNull();
  });

  it("navigates to the next/previous page and disables buttons at the ends", () => {
    render(<DataTable columns={columns} data={makeRows(45)} pageSize={20} />);
    const [prev, next] = Array.from(container.querySelectorAll("button"));
    expect(prev.hasAttribute("disabled")).toBe(true);
    expect(next.hasAttribute("disabled")).toBe(false);

    click(next);
    expect(rowValues()).toEqual([
      "21",
      "22",
      "23",
      "24",
      "25",
      "26",
      "27",
      "28",
      "29",
      "30",
      "31",
      "32",
      "33",
      "34",
      "35",
      "36",
      "37",
      "38",
      "39",
      "40",
    ]);
    expect(prev.hasAttribute("disabled")).toBe(false);

    click(next);
    expect(rowValues()).toEqual(["41", "42", "43", "44", "45"]);
    expect(next.hasAttribute("disabled")).toBe(true);

    click(prev);
    click(prev);
    expect(rowValues()[0]).toBe("1");
  });
});
