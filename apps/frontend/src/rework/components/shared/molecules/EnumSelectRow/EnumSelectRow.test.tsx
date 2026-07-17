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

// Coverage for EnumSelectRow's listbox interaction, now built from the
// shared MenuPopover/MenuPopoverItem primitives instead of a bespoke
// ul/li/button implementation. These tests pin the interaction contract so
// that consolidation could not silently regress keyboard nav or focus
// restoration.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EnumSelectRow, type EnumSelectOption } from "./EnumSelectRow.tsx";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS: EnumSelectOption<"a" | "b" | "c">[] = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

let container: HTMLDivElement;
let root: Root;

function Harness({ onChange }: { onChange: (v: "a" | "b" | "c") => void }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState<"a" | "b" | "c">("a");
  return (
    <EnumSelectRow
      icon={{ category: "outlined", type: "tune" }}
      label="Policy"
      title="Search policy"
      value={value}
      options={OPTIONS}
      open={open}
      onToggle={() => setOpen((o) => !o)}
      onChange={(v) => {
        setValue(v);
        setOpen(false);
        onChange(v);
      }}
    />
  );
}

function render(onChange: (v: "a" | "b" | "c") => void = () => {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<Harness onChange={onChange} />);
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

function options(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('[role="option"]'));
}

function click(el: HTMLElement) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function pressKey(el: HTMLElement, key: string) {
  act(() => {
    el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

describe("EnumSelectRow", () => {
  it("opens the listbox on trigger click and focuses the selected option", () => {
    render();
    expect(container.querySelector('[role="listbox"]')).toBeNull();

    click(trigger());

    expect(container.querySelector('[role="listbox"]')).not.toBeNull();
    expect(options()).toHaveLength(3);
    expect(document.activeElement).toBe(options()[0]);
  });

  it("ArrowDown/ArrowUp move focus between options, Home/End jump to first/last", () => {
    render();
    click(trigger());
    const [first, second, third] = options();

    pressKey(first, "ArrowDown");
    expect(document.activeElement).toBe(second);

    pressKey(second, "ArrowDown");
    expect(document.activeElement).toBe(third);

    pressKey(third, "Home");
    expect(document.activeElement).toBe(first);

    pressKey(first, "End");
    expect(document.activeElement).toBe(third);
  });

  it("only one option participates in the roving tab order at a time", () => {
    render();
    click(trigger());
    const [first, second, third] = options();
    expect(first.tabIndex).toBe(0);
    expect(second.tabIndex).toBe(-1);
    expect(third.tabIndex).toBe(-1);

    pressKey(first, "ArrowDown");
    expect(options()[0].tabIndex).toBe(-1);
    expect(options()[1].tabIndex).toBe(0);
  });

  it("Escape closes the listbox and restores focus to the trigger", () => {
    render();
    click(trigger());
    pressKey(options()[0], "Escape");

    expect(container.querySelector('[role="listbox"]')).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("selecting an option by click calls onChange, closes the listbox, and restores trigger focus", () => {
    const onChange = vi.fn();
    render(onChange);
    click(trigger());

    click(options()[1]);

    expect(onChange).toHaveBeenCalledWith("b");
    expect(container.querySelector('[role="listbox"]')).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("marks the selected option via aria-selected and a trailing check icon, and announces the current value on the trigger", () => {
    render();
    click(trigger());
    const [first, second] = options();

    expect(first.getAttribute("aria-selected")).toBe("true");
    expect(second.getAttribute("aria-selected")).toBe("false");
    expect(first.querySelector(".material-symbols-outlined")).not.toBeNull();

    expect(trigger().getAttribute("aria-label")).toBe("Search policy: Alpha");
  });
});
