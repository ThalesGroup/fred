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

// Regression coverage: the document name is a nested <button> that stops
// propagation so the row's own onClick doesn't also fire. It used to call ONLY
// onPreview, so opening a document by clicking its name left the selection
// highlight stranded on the previously selected row.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

// No active task for any row — the intrinsic `status` prop then decides.
vi.mock("react-redux", () => ({
  useSelector: () => undefined,
}));

import { DocRow } from "./DocRow";

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function render(node: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(node);
  });
}

describe("DocRow — selection follows a click on the document name", () => {
  it("selects the row AND opens the preview when the name is clicked", () => {
    const onSelect = vi.fn();
    const onPreview = vi.fn();
    render(<DocRow id="doc-1" name="facture.pdf" fileType="pdf" onSelect={onSelect} onPreview={onPreview} />);

    const nameButton = container.querySelector("button");
    act(() => {
      nameButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onPreview).toHaveBeenCalledTimes(1);
    // The bug: this was 0 — the highlight stayed on the previous row.
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("still selects only once — the row's own handler must not double-fire", () => {
    const onSelect = vi.fn();
    render(<DocRow id="doc-1" name="facture.pdf" fileType="pdf" onSelect={onSelect} onPreview={() => {}} />);

    act(() => {
      container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("marks the row as selected so the highlight can be styled", () => {
    render(<DocRow id="doc-1" name="facture.pdf" fileType="pdf" selected onPreview={() => {}} />);
    expect(container.firstElementChild?.getAttribute("data-selected")).toBe("true");
  });
});
