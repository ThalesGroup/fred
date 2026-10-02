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
import Switch, { type SwitchProps } from "./Switch.tsx";

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

describe("Switch", () => {
  it("defaults to the medium size", () => {
    render(<Switch aria-label="toggle" />);
    expect(container.querySelector("label")?.dataset.size).toBe("medium");
  });

  it("applies the small size without leaking it to the native input", () => {
    render(<Switch size="small" aria-label="toggle" />);
    expect(container.querySelector("label")?.dataset.size).toBe("small");
    expect(container.querySelector("input")?.hasAttribute("size")).toBe(false);
  });
});

it("keeps checkbox behavior for an untyped consumer passing another input type", () => {
  const props = { type: "text", "aria-label": "toggle" } as unknown as SwitchProps;
  render(<Switch {...props} />);
  const input = container.querySelector("input")!;
  expect(input.type).toBe("checkbox");
  expect(input.checked).toBe(false);
  act(() => input.click());
  expect(input.checked).toBe(true);
});

it("merges consumer classes with the native checkbox styling", () => {
  render(<Switch className="consumer-switch" aria-label="toggle" />);
  const input = container.querySelector("input")!;
  expect(input.className).toContain("native-input");
  expect(input.classList.contains("consumer-switch")).toBe(true);
  act(() => input.click());
  expect(input.checked).toBe(true);
});
