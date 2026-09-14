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

// The review dialog writes overrides, never edits the inventory itself: the
// include switch, the intent select, and a zone role from the detail view all
// go through `onOverride` with the pattern id and the patch.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Pattern, TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options?.label ? `${key}:${options.label}` : key),
  }),
}));
vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => <div data-testid="pdf">{children}</div>,
  Page: ({ pageNumber }: { pageNumber: number }) => <div data-testid={`page-${pageNumber}`} />,
  pdfjs: { GlobalWorkerOptions: {} },
}));
vi.mock("./usePatternsPreview", () => ({
  usePatternsPreview: () => ({ objectUrl: "blob:pdf", isLoading: false, error: null }),
}));
vi.mock("@shared/molecules/Dialog/Dialog.tsx", () => ({
  Dialog: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div role="dialog" aria-label={title}>
      {children}
    </div>
  ),
}));
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    value,
    onChange,
    ariaLabel,
  }: {
    options: { value: string; label: string }[];
    value: string;
    onChange: (v: string) => void;
    ariaLabel: string;
  }) => (
    <select aria-label={ariaLabel} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { PatternReviewDialog } from "./PatternReviewDialog";

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
  act(() => root.unmount());
  container.remove();
});

const box = { x: 100, y: 100, w: 500, h: 200 };

function pattern(overrides: Partial<Pattern>): Pattern {
  return {
    id: "layout:0",
    source: "layout",
    source_index: 0,
    name: "Cover",
    label: "Cover",
    intent: "title",
    zones: [{ key: "ph:0", role: "title", box, sample: "Titre" }],
    groups: [],
    included: true,
    preferred: false,
    warnings: [],
    ...overrides,
  };
}

const INVENTORY: TemplateInventory = {
  slide_width: 1,
  slide_height: 1,
  patterns: [
    pattern({}),
    pattern({
      id: "slide:9",
      source: "slide",
      source_index: 9,
      label: "Chart",
      intent: "content",
      included: false,
      exclusion_reason: "chart",
    }),
  ],
  shared_texts: [],
};

function select(label: string): HTMLSelectElement {
  const element = container.querySelector(`select[aria-label="${label}"]`);
  if (!element) throw new Error(`no select ${label}`);
  return element as HTMLSelectElement;
}

describe("PatternReviewDialog", () => {
  it("renders one thumbnail page per pattern and folds the excluded ones", () => {
    render(
      <PatternReviewDialog
        open
        inventory={INVENTORY}
        previewSource={{ kind: "theme" }}
        readOnly={false}
        onOverride={() => {}}
        onClose={() => {}}
      />,
    );
    expect(container.querySelector('[data-testid="page-1"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="page-2"]')).not.toBeNull();
    expect(container.querySelector("details summary")?.textContent).toBe("capability.ppt_builder.review.excluded");
  });

  it("writes include and intent corrections as overrides", () => {
    const onOverride = vi.fn();
    render(
      <PatternReviewDialog
        open
        inventory={INVENTORY}
        previewSource={{ kind: "theme" }}
        readOnly={false}
        onOverride={onOverride}
        onClose={() => {}}
      />,
    );
    const toggle = container.querySelector(
      'input[aria-label="capability.ppt_builder.review.include:Cover"]',
    ) as HTMLInputElement;
    act(() => {
      toggle.click();
    });
    expect(onOverride).toHaveBeenCalledWith("layout:0", { included: false });

    const intent = select("capability.ppt_builder.review.intentFor:Cover");
    act(() => {
      intent.value = "section";
      intent.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(onOverride).toHaveBeenLastCalledWith("layout:0", { intent: "section" });
  });

  it("opens the detail from the thumbnail and writes a zone role", () => {
    const onOverride = vi.fn();
    render(
      <PatternReviewDialog
        open
        inventory={INVENTORY}
        previewSource={{ kind: "theme" }}
        readOnly={false}
        onOverride={onOverride}
        onClose={() => {}}
      />,
    );
    const thumbnail = container.querySelector('button[aria-label="Cover"]') as HTMLButtonElement;
    act(() => {
      thumbnail.click();
    });
    // The detail draws the zone outline at the analysis geometry.
    const outline = container.querySelector('[data-role="title"]') as HTMLElement;
    expect(outline.style.left).toBe("10%");
    expect(outline.style.width).toBe("50%");
    const role = select("capability.ppt_builder.review.roleFor");
    act(() => {
      role.value = "keep";
      role.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(onOverride).toHaveBeenCalledWith("layout:0", { zone_roles: { "ph:0": "keep" } });
  });

  it("disables every correction in read-only mode", () => {
    render(
      <PatternReviewDialog
        open
        inventory={INVENTORY}
        previewSource={{ kind: "theme" }}
        readOnly
        onOverride={() => {}}
        onClose={() => {}}
      />,
    );
    const toggle = container.querySelector(
      'input[aria-label="capability.ppt_builder.review.include:Cover"]',
    ) as HTMLInputElement;
    expect(toggle.disabled).toBe(true);
  });
});
