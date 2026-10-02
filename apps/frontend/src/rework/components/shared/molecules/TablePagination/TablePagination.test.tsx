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
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import TablePagination from "./TablePagination.tsx";

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

/** [rowsPerPageSelect?, first, prev, next, last] */
function buttons(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll("button"));
}

const baseProps = {
  totalItems: 45,
  currentPage: 1,
  pageCount: 3,
  rowsPerPage: 20,
  rowsPerPageOptions: [
    { value: 20, label: "20", key: "20" },
    { value: 50, label: "50", key: "50" },
  ],
  onFirst: vi.fn(),
  onPrev: vi.fn(),
  onNext: vi.fn(),
  onLast: vi.fn(),
};

describe("TablePagination", () => {
  it("shows the total item count and current/total page", () => {
    render(<TablePagination {...baseProps} />);
    expect(container.textContent).toContain("45");
    expect(container.textContent).toContain("Page 2 of 3");
  });

  it("hides the rows-per-page selector when onRowsPerPageChange is omitted", () => {
    render(<TablePagination {...baseProps} />);
    expect(buttons()).toHaveLength(4);
  });

  it("shows the rows-per-page selector when onRowsPerPageChange is provided", () => {
    render(<TablePagination {...baseProps} onRowsPerPageChange={vi.fn()} />);
    expect(buttons()).toHaveLength(5);
  });

  it("calls the nav callbacks with no arguments — the caller owns page math", () => {
    const onFirst = vi.fn();
    const onPrev = vi.fn();
    const onNext = vi.fn();
    const onLast = vi.fn();
    render(<TablePagination {...baseProps} onFirst={onFirst} onPrev={onPrev} onNext={onNext} onLast={onLast} />);

    const [first, prev, next, last] = buttons();
    click(first);
    click(prev);
    click(next);
    click(last);

    expect(onFirst).toHaveBeenCalledTimes(1);
    expect(onPrev).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onLast).toHaveBeenCalledTimes(1);
  });

  it("disables first/prev on the first page and next/last on the last page", () => {
    render(<TablePagination {...baseProps} currentPage={0} pageCount={1} />);
    const [first, prev, next, last] = buttons();
    expect(first.hasAttribute("disabled")).toBe(true);
    expect(prev.hasAttribute("disabled")).toBe(true);
    expect(next.hasAttribute("disabled")).toBe(true);
    expect(last.hasAttribute("disabled")).toBe(true);
  });
});

it("names the size selector using caller-owned localized text", () => {
  render(
    <TablePagination {...baseProps} labels={{ itemsPerPage: "Éléments par page" }} onRowsPerPageChange={vi.fn()} />,
  );
  expect(container.querySelector('button[aria-label="Éléments par page"]')).not.toBeNull();
});

it("retains defaults for explicitly undefined partial labels", () => {
  render(
    <TablePagination
      {...baseProps}
      labels={{ totalItems: undefined, pageNumber: undefined, itemsPerPage: undefined, first: undefined }}
      onRowsPerPageChange={vi.fn()}
    />,
  );
  expect(container.textContent).toContain("45 items");
  expect(container.textContent).toContain("Page 2 of 3");
  expect(container.querySelector('[aria-label="Items per page"]')).not.toBeNull();
  expect(container.querySelector('[aria-label="First page"]')).not.toBeNull();
});

it("navigates from an enclosing form without submitting it", () => {
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
  const callbacks = [vi.fn(), vi.fn(), vi.fn(), vi.fn()];
  render(
    <form onSubmit={submit}>
      <TablePagination
        {...baseProps}
        onFirst={callbacks[0]}
        onPrev={callbacks[1]}
        onNext={callbacks[2]}
        onLast={callbacks[3]}
      />
    </form>,
  );
  for (const button of buttons()) act(() => button.click());
  callbacks.forEach((callback) => expect(callback).toHaveBeenCalledOnce());
  expect(submit).not.toHaveBeenCalled();
});

it.each([{ options: [] }, { options: baseProps.rowsPerPageOptions }])(
  "displays an active size missing from standalone options %j",
  ({ options }) => {
    render(
      <TablePagination {...baseProps} rowsPerPage={25} rowsPerPageOptions={options} onRowsPerPageChange={vi.fn()} />,
    );
    expect(buttons()[0].textContent).toContain("25");
    act(() =>
      root.render(
        <TablePagination {...baseProps} rowsPerPage={37} rowsPerPageOptions={options} onRowsPerPageChange={vi.fn()} />,
      ),
    );
    expect(buttons()[0].textContent).toContain("37");
    expect(options).not.toContainEqual(expect.objectContaining({ value: 25 }));
  },
);

it("preserves the caller label for an existing active option", () => {
  render(
    <TablePagination
      {...baseProps}
      rowsPerPage={25}
      rowsPerPageOptions={[{ key: "custom", value: 25, label: "Twenty-five" }]}
      onRowsPerPageChange={vi.fn()}
    />,
  );
  expect(buttons()[0].textContent).toContain("Twenty-five");
});

it("normalizes zero pages for the formatter and disables navigation", () => {
  const pageNumber = vi.fn((page: number, count: number) => `${page}/${count}`);
  render(<TablePagination {...baseProps} totalItems={0} currentPage={0} pageCount={0} labels={{ pageNumber }} />);
  expect(pageNumber).toHaveBeenCalledWith(1, 1);
  expect(container.textContent).toContain("1/1");
  expect(buttons().every((button) => button.disabled)).toBe(true);
});

it.each([-1, 2, 4, NaN, Infinity, 0.5])("rejects an invalid controlled current page %s", (currentPage) => {
  render(<TablePagination {...baseProps} />);
  expect(() =>
    renderToStaticMarkup(<TablePagination {...baseProps} pageCount={2} currentPage={currentPage} />),
  ).toThrow("currentPage must be within pageCount");
});
it("accepts an atomic page-count shrink with a corrected index", () => {
  render(<TablePagination {...baseProps} pageCount={5} currentPage={4} />);
  act(() => root.render(<TablePagination {...baseProps} pageCount={2} currentPage={1} />));
  expect(container.textContent).toContain("Page 2 of 2");
});

it.each([-1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])("rejects invalid totalItems %s", (totalItems) => {
  render(<TablePagination {...baseProps} />);
  expect(() => renderToStaticMarkup(<TablePagination {...baseProps} totalItems={totalItems} />)).toThrow(
    "totalItems must be a nonnegative safe integer",
  );
});

// Validate both incoming state and values the selector can send back to its owner.
it.each([0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])("rejects invalid page sizes %s", (value) => {
  render(<TablePagination {...baseProps} />);
  for (const onRowsPerPageChange of [undefined, vi.fn()]) {
    expect(() =>
      renderToStaticMarkup(
        <TablePagination {...baseProps} rowsPerPage={value} onRowsPerPageChange={onRowsPerPageChange} />,
      ),
    ).toThrow("rowsPerPage must be a positive safe integer");
    expect(() =>
      renderToStaticMarkup(
        <TablePagination
          {...baseProps}
          rowsPerPageOptions={[...baseProps.rowsPerPageOptions, { key: "invalid", label: "Invalid", value }]}
          onRowsPerPageChange={onRowsPerPageChange}
        />,
      ),
    ).toThrow("rowsPerPageOptions values must be positive safe integers");
  }
});
