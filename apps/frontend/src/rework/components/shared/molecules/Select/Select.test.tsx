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

// Regression coverage: Home/End previously jumped straight to index 0 / the
// last index regardless of whether that option was disabled. Confirmed
// mechanism: `handleTriggerKeyDown`'s Home/End cases called
// `setActiveIndex(0)` / `setActiveIndex(options.length - 1)` directly. Fixed
// to walk to the first/last *enabled* option, matching the arrow-key
// disabled-skip behavior that already existed.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import Select from "./Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";

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

function trigger(): HTMLButtonElement {
  return container.querySelector("button") as HTMLButtonElement;
}

function pressKey(key: string) {
  act(() => {
    trigger().dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

function activeDescendantLabel(options: OptionModel<string>[]): string | undefined {
  const id = trigger().getAttribute("aria-activedescendant");
  if (!id) return undefined;
  const value = id.split("-opt-")[1];
  return options.find((o) => String(o.value) === value)?.label;
}

describe("Select keyboard navigation — disabled options", () => {
  it("Home selects the first enabled option when the literal first option is disabled", () => {
    const options: OptionModel<string>[] = [
      { key: "a", value: "a", label: "A", disabled: true },
      { key: "b", value: "b", label: "B" },
      { key: "c", value: "c", label: "C" },
    ];
    render(<Select options={options} onChange={() => {}} size="medium" />);

    pressKey("ArrowDown"); // open
    pressKey("End");
    pressKey("Home");

    expect(activeDescendantLabel(options)).toBe("B");
  });

  it("End selects the last enabled option when the literal last option is disabled", () => {
    const options: OptionModel<string>[] = [
      { key: "a", value: "a", label: "A" },
      { key: "b", value: "b", label: "B" },
      { key: "c", value: "c", label: "C", disabled: true },
    ];
    render(<Select options={options} onChange={() => {}} size="medium" />);

    pressKey("ArrowDown"); // open, active = A
    pressKey("End");

    expect(activeDescendantLabel(options)).toBe("B");
  });

  it("does not crash and leaves no active descendant when every option is disabled", () => {
    const options: OptionModel<string>[] = [
      { key: "a", value: "a", label: "A", disabled: true },
      { key: "b", value: "b", label: "B", disabled: true },
    ];
    render(<Select options={options} onChange={() => {}} size="medium" />);

    expect(() => {
      pressKey("ArrowDown"); // open
      pressKey("Home");
      pressKey("End");
      pressKey("ArrowDown");
    }).not.toThrow();

    expect(trigger().hasAttribute("aria-activedescendant")).toBe(false);
  });

  it("opening with a disabled selected option activates the first enabled option instead", () => {
    const options: OptionModel<string>[] = [
      { key: "a", value: "a", label: "A", disabled: true },
      { key: "b", value: "b", label: "B" },
    ];
    render(<Select options={options} value="a" onChange={() => {}} size="medium" />);

    pressKey("ArrowDown"); // open

    expect(activeDescendantLabel(options)).toBe("B");
  });

  it("Enter/Space cannot activate a disabled option", () => {
    const onChange = vi.fn();
    const options: OptionModel<string>[] = [
      { key: "a", value: "a", label: "A", disabled: true },
      { key: "b", value: "b", label: "B" },
    ];
    render(<Select options={options} onChange={onChange} size="medium" />);

    pressKey("ArrowDown"); // open, active jumps to B (A is disabled)
    pressKey("ArrowUp"); // wrap back — still skips disabled A, stays on B
    pressKey("Enter");

    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("Arrow navigation wraps around while skipping disabled options", () => {
    const options: OptionModel<string>[] = [
      { key: "a", value: "a", label: "A" },
      { key: "b", value: "b", label: "B", disabled: true },
      { key: "c", value: "c", label: "C" },
    ];
    render(<Select options={options} onChange={() => {}} size="medium" />);

    pressKey("ArrowDown"); // open, active = A
    pressKey("ArrowDown"); // A -> C (B disabled)
    expect(activeDescendantLabel(options)).toBe("C");

    pressKey("ArrowDown"); // C -> A (wraps, B disabled)
    expect(activeDescendantLabel(options)).toBe("A");

    pressKey("ArrowUp"); // A -> C (wraps backward, B disabled)
    expect(activeDescendantLabel(options)).toBe("C");
  });
});
