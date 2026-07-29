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
import BulkActionsBar from "./BulkActionsBar.tsx";

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

describe("BulkActionsBar", () => {
  it("renders nothing when no row is selected", () => {
    render(<BulkActionsBar selectedCount={0} onDelete={vi.fn()} onClearSelection={vi.fn()} />);
    expect(container.querySelector("button")).toBeNull();
  });

  it("shows Delete + Clear when onExcludeFromSearch is omitted (non-Corpus tabs)", () => {
    render(<BulkActionsBar selectedCount={2} onDelete={vi.fn()} onClearSelection={vi.fn()} />);
    expect(container.querySelectorAll("button")).toHaveLength(2);
  });

  it("shows Exclude + Delete + Clear when onExcludeFromSearch is provided (Corpus tab)", () => {
    render(
      <BulkActionsBar selectedCount={2} onDelete={vi.fn()} onClearSelection={vi.fn()} onExcludeFromSearch={vi.fn()} />,
    );
    expect(container.querySelectorAll("button")).toHaveLength(3);
  });

  it("invokes the right callback for each button", () => {
    const onDelete = vi.fn();
    const onClearSelection = vi.fn();
    const onExcludeFromSearch = vi.fn();
    render(
      <BulkActionsBar
        selectedCount={3}
        onDelete={onDelete}
        onClearSelection={onClearSelection}
        onExcludeFromSearch={onExcludeFromSearch}
      />,
    );
    const [excludeButton, deleteButton, clearButton] = Array.from(container.querySelectorAll("button"));

    click(excludeButton);
    expect(onExcludeFromSearch).toHaveBeenCalledOnce();
    expect(onDelete).not.toHaveBeenCalled();
    expect(onClearSelection).not.toHaveBeenCalled();

    click(deleteButton);
    expect(onDelete).toHaveBeenCalledOnce();
    expect(onClearSelection).not.toHaveBeenCalled();

    click(clearButton);
    expect(onClearSelection).toHaveBeenCalledOnce();
  });

  it("shows the 'Selection: N' count label", () => {
    render(<BulkActionsBar selectedCount={5} onDelete={vi.fn()} onClearSelection={vi.fn()} />);
    expect(container.textContent).toContain('rework.resources.bulkActions.selectedCount {"count":5}');
  });

  it("hides Download when onDownload is omitted", () => {
    render(<BulkActionsBar selectedCount={2} onDelete={vi.fn()} onClearSelection={vi.fn()} />);
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.download"]')).toBeNull();
  });

  it("shows Download, positioned before Delete, when onDownload is provided", () => {
    render(<BulkActionsBar selectedCount={2} onDelete={vi.fn()} onClearSelection={vi.fn()} onDownload={vi.fn()} />);
    const buttons = Array.from(container.querySelectorAll("button"));
    const downloadIndex = buttons.findIndex(
      (b) => b.getAttribute("aria-label") === "rework.resources.bulkActions.download",
    );
    const deleteIndex = buttons.findIndex(
      (b) => b.getAttribute("aria-label") === "rework.resources.bulkActions.delete",
    );
    expect(downloadIndex).toBeGreaterThanOrEqual(0);
    expect(downloadIndex).toBeLessThan(deleteIndex);
  });

  it("invokes onDownload without triggering delete/clear", () => {
    const onDownload = vi.fn();
    const onDelete = vi.fn();
    const onClearSelection = vi.fn();
    render(
      <BulkActionsBar
        selectedCount={2}
        onDelete={onDelete}
        onClearSelection={onClearSelection}
        onDownload={onDownload}
      />,
    );

    click(container.querySelector('button[aria-label="rework.resources.bulkActions.download"]'));

    expect(onDownload).toHaveBeenCalledOnce();
    expect(onDelete).not.toHaveBeenCalled();
    expect(onClearSelection).not.toHaveBeenCalled();
  });

  it("shows all four actions when both onExcludeFromSearch and onDownload are provided", () => {
    render(
      <BulkActionsBar
        selectedCount={2}
        onDelete={vi.fn()}
        onClearSelection={vi.fn()}
        onExcludeFromSearch={vi.fn()}
        onDownload={vi.fn()}
      />,
    );
    expect(container.querySelectorAll("button")).toHaveLength(4);
  });

  it("disables the download button while downloadLoading is true", () => {
    render(
      <BulkActionsBar
        selectedCount={2}
        onDelete={vi.fn()}
        onClearSelection={vi.fn()}
        onDownload={vi.fn()}
        downloadLoading
      />,
    );

    const downloadButton = container.querySelector(
      'button[aria-label="rework.resources.bulkActions.download"]',
    ) as HTMLButtonElement;
    expect(downloadButton.disabled).toBe(true);
    expect(downloadButton.getAttribute("aria-busy")).toBe("true");
  });

  it("keeps the download button enabled when downloadLoading is false/omitted", () => {
    render(<BulkActionsBar selectedCount={2} onDelete={vi.fn()} onClearSelection={vi.fn()} onDownload={vi.fn()} />);

    const downloadButton = container.querySelector(
      'button[aria-label="rework.resources.bulkActions.download"]',
    ) as HTMLButtonElement;
    expect(downloadButton.disabled).toBe(false);
  });
});
