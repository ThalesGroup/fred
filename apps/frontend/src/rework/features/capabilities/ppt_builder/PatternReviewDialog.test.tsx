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
// include switch, the kind select and the label all go through `onOverride`.

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
    disabled,
  }: {
    options: { value: string; label: string }[];
    value: string;
    onChange: (v: string) => void;
    ariaLabel: string;
    disabled?: boolean;
  }) => (
    <select aria-label={ariaLabel} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
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

// happy-dom lays nothing out: give every thumbnail box a width so its page renders.
Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 220 });

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

function pattern(overrides: Partial<Pattern>): Pattern {
  return {
    id: "layout:0",
    source: "layout",
    source_index: 0,
    name: "Cover",
    label: "Cover",
    kind: "cover",
    included: true,
    ...overrides,
  };
}

const INVENTORY: TemplateInventory = {
  slide_width: 1,
  slide_height: 1,
  patterns: [
    pattern({}),
    pattern({ id: "slide:2", source: "slide", source_index: 2, label: "Agenda", kind: "bullets" }),
    pattern({
      id: "slide:9",
      source: "slide",
      source_index: 9,
      label: "Chart",
      kind: "other",
      included: false,
      exclusion_reason: "chart",
      labelled_by: "heuristic",
    }),
  ],
};

function renderDialog(onOverride = vi.fn(), readOnly = false) {
  render(
    <PatternReviewDialog
      open
      inventory={INVENTORY}
      previewSource={{ kind: "builtin" }}
      readOnly={readOnly}
      onOverride={onOverride}
      onClose={() => {}}
    />,
  );
  return onOverride;
}

function input(label: string): HTMLInputElement {
  const element = container.querySelector(`[aria-label="${label}"]`);
  if (!element) throw new Error(`no control ${label}`);
  return element as HTMLInputElement;
}

describe("PatternReviewDialog", () => {
  it("renders one thumbnail page per pattern, keyed by its place in the inventory", () => {
    renderDialog();
    for (const page of [1, 2, 3]) expect(container.querySelector(`[data-testid="page-${page}"]`)).not.toBeNull();
    const pageIn = (section: string) =>
      [...container.querySelectorAll(`[data-section="${section}"] [data-testid^="page-"]`)].map((e) =>
        e.getAttribute("data-testid"),
      );
    expect(pageIn("slides")).toEqual(["page-2"]);
    expect(pageIn("layouts")).toEqual(["page-1"]);
    expect(pageIn("excluded")).toEqual(["page-3"]);
    expect(container.textContent).toContain("capability.ppt_builder.review.labelledByRules");
  });

  it("shows the deck's slides first, then the layouts folded with their hint, then the excluded", () => {
    renderDialog();
    const sections = [...container.querySelectorAll("[data-section]")];
    expect(sections.map((s) => s.getAttribute("data-section"))).toEqual(["slides", "layouts", "excluded"]);
    expect(sections[0].tagName).toBe("SECTION");
    const layouts = sections[1] as HTMLDetailsElement;
    expect(layouts.tagName).toBe("DETAILS");
    expect(layouts.open).toBe(false);
    expect(layouts.querySelector("summary")?.textContent).toBe("capability.ppt_builder.review.layouts");
    expect(layouts.textContent).toContain("capability.ppt_builder.review.layoutsHint");
    expect((sections[2] as HTMLDetailsElement).open).toBe(false);
    expect(sections[2].querySelector("summary")?.textContent).toBe("capability.ppt_builder.review.excluded");
  });

  it("puts an excluded layout with the excluded, and drops empty sections", () => {
    render(
      <PatternReviewDialog
        open
        inventory={{ ...INVENTORY, patterns: [pattern({ included: false, exclusion_reason: "author" })] }}
        previewSource={{ kind: "builtin" }}
        readOnly={false}
        onOverride={vi.fn()}
        onClose={() => {}}
      />,
    );
    const sections = [...container.querySelectorAll("[data-section]")];
    expect(sections.map((s) => s.getAttribute("data-section"))).toEqual(["excluded"]);
  });

  it("writes include, kind and label corrections as overrides", () => {
    const onOverride = renderDialog();
    act(() => {
      input("capability.ppt_builder.review.include:Cover").click();
    });
    expect(onOverride).toHaveBeenCalledWith("layout:0", { included: false });

    const kind = input("capability.ppt_builder.review.kindFor:Cover") as unknown as HTMLSelectElement;
    act(() => {
      kind.value = "section";
      kind.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(onOverride).toHaveBeenLastCalledWith("layout:0", { kind: "section" });

    const label = input("capability.ppt_builder.review.labelFor:Cover");
    act(() => {
      label.focus();
      label.value = "Front page";
      label.blur();
    });
    expect(onOverride).toHaveBeenLastCalledWith("layout:0", { label: "Front page" });
  });

  it("has no zone-role editing any more", () => {
    renderDialog();
    expect(container.querySelector('[aria-label^="capability.ppt_builder.review.roleFor"]')).toBeNull();
    expect(container.querySelector("[data-role]")).toBeNull();
  });

  it("disables every correction in read-only mode", () => {
    renderDialog(vi.fn(), true);
    expect(input("capability.ppt_builder.review.include:Cover").disabled).toBe(true);
    expect(input("capability.ppt_builder.review.labelFor:Cover").disabled).toBe(true);
    expect((input("capability.ppt_builder.review.kindFor:Cover") as unknown as HTMLSelectElement).disabled).toBe(true);
  });
});
