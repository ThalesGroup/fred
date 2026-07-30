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

// Coverage for the generic "card with a header and a table" contract
// extracted from the Corpus d'équipe tab (FRONT-09.H/RFC §13.7) — this
// component knows nothing about documents or tags; it only renders what
// it's given (columns/rows/breadcrumb/toolbar slot) and reports interaction
// back through callbacks.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResourceExplorer from "./ResourceExplorer.tsx";
import type { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";

// DataTable (rendered internally, unmocked) calls useTranslation for its
// pagination footer — same mock DataTable's own test file uses.
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
  name: string;
}

const columns: DataTableColumn<Row>[] = [{ label: "Name", cellRenderer: (row) => <span>{row.name}</span> }];

function makeRows(count: number): Row[] {
  return Array.from({ length: count }, (_, i) => ({ id: i + 1, name: `Row ${i + 1}` }));
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

function backButton(): HTMLButtonElement {
  const button = container.querySelector('button[aria-label="Back"]');
  if (!button) throw new Error("back button not rendered");
  return button as HTMLButtonElement;
}

const baseBreadcrumb = { segments: [{ label: "Root" }], onBack: () => {}, canGoBack: false, backLabel: "Back" };

describe("ResourceExplorer", () => {
  it("renders caller-supplied toolbar content", () => {
    render(
      <ResourceExplorer<Row>
        breadcrumb={baseBreadcrumb}
        toolbarActions={<button>Custom action</button>}
        columns={columns}
        rows={makeRows(1)}
        rowKey={(r) => r.id}
      />,
    );
    expect([...container.querySelectorAll("button")].some((b) => b.textContent === "Custom action")).toBe(true);
  });

  it("hides and disables the back button when canGoBack is false, enables it when true", () => {
    render(<ResourceExplorer<Row> breadcrumb={baseBreadcrumb} columns={columns} rows={[]} rowKey={(r) => r.id} />);
    expect(backButton().hasAttribute("disabled")).toBe(true);
    expect(backButton().style.visibility).toBe("hidden");

    const onBack = vi.fn();
    render(
      <ResourceExplorer<Row>
        breadcrumb={{ ...baseBreadcrumb, canGoBack: true, onBack }}
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
      />,
    );
    expect(backButton().hasAttribute("disabled")).toBe(false);
    click(backButton());
    expect(onBack).toHaveBeenCalled();
  });

  it("omits the search box entirely when `search` is not provided", () => {
    render(<ResourceExplorer<Row> breadcrumb={baseBreadcrumb} columns={columns} rows={[]} rowKey={(r) => r.id} />);
    expect(container.querySelector("input[type=text]")).toBeNull();
  });

  it("renders the search box and reports typed input", () => {
    const onChange = vi.fn();
    render(
      <ResourceExplorer<Row>
        breadcrumb={baseBreadcrumb}
        search={{ value: "", onChange, placeholder: "Search", ariaLabel: "Search", clearAriaLabel: "Clear" }}
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
      />,
    );
    const input = container.querySelector("input[type=text]") as HTMLInputElement;
    expect(input).not.toBeNull();
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "abc");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(onChange).toHaveBeenCalledWith("abc");
  });

  it("loading, empty, and the table are mutually exclusive", () => {
    render(
      <ResourceExplorer<Row>
        breadcrumb={baseBreadcrumb}
        loading
        loadingMessage="Loading…"
        columns={columns}
        rows={makeRows(2)}
        rowKey={(r) => r.id}
      />,
    );
    expect(container.textContent).toContain("Loading…");
    expect(container.querySelectorAll("table, [role=table]")).toHaveLength(0);
  });

  it("shows the empty message instead of the table when empty is true", () => {
    render(
      <ResourceExplorer<Row>
        breadcrumb={baseBreadcrumb}
        empty
        emptyMessage="Nothing here"
        columns={columns}
        rows={makeRows(2)}
        rowKey={(r) => r.id}
      />,
    );
    expect(container.textContent).toContain("Nothing here");
    expect(container.textContent).not.toContain("Row 1");
  });

  it("renders rows via DataTable when neither loading nor empty", () => {
    render(
      <ResourceExplorer<Row> breadcrumb={baseBreadcrumb} columns={columns} rows={makeRows(2)} rowKey={(r) => r.id} />,
    );
    expect(container.textContent).toContain("Row 1");
    expect(container.textContent).toContain("Row 2");
  });

  it("forwards selectedKeys/onSelectedKeysChange to DataTable's row checkboxes", () => {
    const onSelectedKeysChange = vi.fn();
    render(
      <ResourceExplorer<Row>
        breadcrumb={baseBreadcrumb}
        columns={columns}
        rows={makeRows(2)}
        rowKey={(r) => r.id}
        selectedKeys={new Set()}
        onSelectedKeysChange={onSelectedKeysChange}
      />,
    );
    const checkboxes = Array.from(container.querySelectorAll('input[type="checkbox"]'));
    // [0] is the header "select all"; row checkboxes follow.
    expect(checkboxes.length).toBeGreaterThan(1);
    click(checkboxes[1]);
    expect(onSelectedKeysChange).toHaveBeenCalledWith(new Set([1]));
  });
});
