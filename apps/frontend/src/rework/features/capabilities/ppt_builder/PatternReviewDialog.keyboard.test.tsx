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

// With the real Dialog: Enter in a label field confirms (closes) the dialog and
// Escape cancels it, both without a blur. A rename typed just before must survive.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";
import type { OverridePatch } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options?.label ? `${key}:${options.label}` : key),
  }),
}));
vi.mock("react-pdf", () => ({
  Document: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Page: () => <div />,
  pdfjs: { GlobalWorkerOptions: {} },
}));
vi.mock("./usePatternsPreview", () => ({
  usePatternsPreview: () => ({ objectUrl: null, isLoading: false, error: null }),
}));

import { PatternReviewDialog } from "./PatternReviewDialog";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const INVENTORY: TemplateInventory = {
  slide_width: 1,
  slide_height: 1,
  patterns: [
    { id: "slide:1", source: "slide", source_index: 1, name: "Cover", label: "Cover", kind: "cover", included: true },
  ],
};

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.getElementById("modal-portal")?.remove();
});

function renderHarness(onOverride: (id: string, patch: OverridePatch) => void) {
  function Harness() {
    const [open, setOpen] = useState(true);
    return (
      <PatternReviewDialog
        open={open}
        inventory={INVENTORY}
        previewSource={null}
        readOnly={false}
        onOverride={onOverride}
        onClose={() => setOpen(false)}
      />
    );
  }
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<Harness />));
}

function renameThenPress(key: "Enter" | "Escape") {
  const onOverride = vi.fn();
  renderHarness(onOverride);
  const field = document.querySelector(
    '[aria-label="capability.ppt_builder.review.labelFor:Cover"]',
  ) as HTMLInputElement;
  act(() => {
    field.focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(field, "Title slide");
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  act(() => {
    field.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(onOverride).toHaveBeenLastCalledWith("slide:1", { label: "Title slide" });
}

describe("PatternReviewDialog closed from the keyboard", () => {
  it("keeps a rename when Enter closes the dialog", () => renameThenPress("Enter"));
  it("keeps a rename when Escape closes the dialog", () => renameThenPress("Escape"));
});
