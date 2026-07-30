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

import { act, createRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import Checkbox from "./Checkbox.tsx";

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

function input(): HTMLInputElement {
  const el = container.querySelector("input");
  if (!el) throw new Error("input not rendered");
  return el;
}

describe("Checkbox indeterminate", () => {
  it("sets the native DOM .indeterminate property, not just the visual/ARIA state", () => {
    render(<Checkbox indeterminate onChange={() => {}} />);
    expect(input().indeterminate).toBe(true);
    expect(input().getAttribute("aria-checked")).toBe("mixed");
  });

  it("clears .indeterminate once the prop goes back to false", () => {
    render(<Checkbox indeterminate onChange={() => {}} />);
    expect(input().indeterminate).toBe(true);

    act(() => {
      root.render(<Checkbox indeterminate={false} onChange={() => {}} />);
    });
    expect(input().indeterminate).toBe(false);
  });

  it("still forwards a caller-supplied ref to the underlying input", () => {
    const ref = createRef<HTMLInputElement>();
    render(<Checkbox ref={ref} indeterminate onChange={() => {}} />);
    expect(ref.current).toBe(input());
    expect(ref.current?.indeterminate).toBe(true);
  });
});
