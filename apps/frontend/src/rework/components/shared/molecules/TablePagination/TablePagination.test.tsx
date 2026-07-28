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
import TablePagination from "./TablePagination.tsx";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));

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
    expect(container.textContent).toContain('"page":2');
    expect(container.textContent).toContain('"pageCount":3');
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
