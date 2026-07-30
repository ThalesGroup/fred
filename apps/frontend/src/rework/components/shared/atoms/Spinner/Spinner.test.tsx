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
import { afterEach, describe, expect, it } from "vitest";
import { Spinner } from "./Spinner.tsx";

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

function svg(): SVGElement {
  const el = container.querySelector("svg");
  if (!el) throw new Error("svg not rendered");
  return el;
}

describe("Spinner", () => {
  it("announces itself as a status region by default", () => {
    render(<Spinner />);
    expect(svg().getAttribute("role")).toBe("status");
    expect(svg().getAttribute("aria-label")).toBe("Loading");
    expect(svg().hasAttribute("aria-hidden")).toBe(false);
  });

  it("drops its own role/aria-label when decorative — a host with its own accessible label owns the announcement", () => {
    render(<Spinner decorative />);
    expect(svg().hasAttribute("role")).toBe(false);
    expect(svg().hasAttribute("aria-label")).toBe(false);
    expect(svg().getAttribute("aria-hidden")).toBe("true");
  });
});
