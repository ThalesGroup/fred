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
import Autocomplete from "./Autocomplete.tsx";
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

function input(): HTMLInputElement {
  return container.querySelector("input") as HTMLInputElement;
}

function pressKey(key: string) {
  act(() => {
    input().dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

function focusedLabel(): string | null {
  const el = container.querySelector('[role="option"][data-focused="true"]');
  return el ? el.textContent : null;
}

// Object-valued options (like a real candidate user record) are the case
// that motivated keying Menu's item id off `option.key` instead of
// `option.value` — a plain string/number `value` would happen to work
// either way.
interface Candidate {
  id: string;
  name: string;
}

function options(): OptionModel<Candidate>[] {
  return [
    { key: "1", value: { id: "1", name: "Alice" }, label: "Alice" },
    { key: "2", value: { id: "2", name: "Bob" }, label: "Bob" },
    { key: "3", value: { id: "3", name: "Carla" }, label: "Carla" },
  ];
}

describe("Autocomplete keyboard navigation", () => {
  it("focuses the first option by default once the menu is open with results", () => {
    render(
      <Autocomplete<Candidate>
        textInput={{ placeholder: "Search" }}
        minQueryLength={0}
        options={options()}
        onSelect={vi.fn()}
      />,
    );
    act(() => {
      input().focus();
    });

    expect(focusedLabel()).toBe("Alice");
  });

  it("ArrowDown/ArrowUp move the focused option, wrapping at each end", () => {
    render(
      <Autocomplete<Candidate>
        textInput={{ placeholder: "Search" }}
        minQueryLength={0}
        options={options()}
        onSelect={vi.fn()}
      />,
    );
    act(() => {
      input().focus();
    });

    pressKey("ArrowDown");
    expect(focusedLabel()).toBe("Bob");

    pressKey("ArrowDown");
    expect(focusedLabel()).toBe("Carla");

    pressKey("ArrowDown");
    expect(focusedLabel()).toBe("Alice"); // wraps

    pressKey("ArrowUp");
    expect(focusedLabel()).toBe("Carla"); // wraps the other way
  });

  it("Enter selects the currently focused option, clears the query, and closes the menu", () => {
    const onSelect = vi.fn();
    render(
      <Autocomplete<Candidate>
        textInput={{ placeholder: "Search" }}
        minQueryLength={0}
        options={options()}
        onSelect={onSelect}
      />,
    );
    act(() => {
      input().focus();
    });

    pressKey("ArrowDown"); // -> Bob
    pressKey("Enter");

    expect(onSelect).toHaveBeenCalledWith({ id: "2", name: "Bob" });
    expect(input().value).toBe("");
    expect(container.querySelector('[data-open="true"]')).toBeNull();
  });

  it("resets the focused option back to the first one on the next keystroke", () => {
    render(
      <Autocomplete<Candidate>
        textInput={{ placeholder: "Search" }}
        minQueryLength={0}
        options={options()}
        onSelect={vi.fn()}
      />,
    );
    act(() => {
      input().focus();
    });
    pressKey("ArrowDown");
    expect(focusedLabel()).toBe("Bob");

    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(input(), "a");
      input().dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(focusedLabel()).toBe("Alice");
  });
});
