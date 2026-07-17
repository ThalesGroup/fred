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

// Regression coverage: keyboard (arrow/Home/End) activation of a ButtonGroup
// item must run through the exact same path as a mouse click, so consumers
// that only wire an item-level `onClick` (e.g. ReleaseNotesContent's version
// tabs, UserSettingsPage's theme/language radio groups) actually update
// state on keyboard navigation, not just the visual selected state.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import ButtonGroup from "./ButtonGroup.tsx";
import type { ButtonGroupItemProps } from "./ButtonGroupItem/ButtonGroupItem.tsx";

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

function items(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll("button"));
}

function pressKey(el: HTMLElement, key: string) {
  act(() => {
    el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

describe("ButtonGroup keyboard activation", () => {
  it("ArrowRight moves focus AND fires the target item's onClick exactly once (uncontrolled, no onSelectedIndexChange)", () => {
    const onClickA = vi.fn();
    const onClickB = vi.fn();
    const groupItems: ButtonGroupItemProps[] = [
      { label: "A", onClick: onClickA },
      { label: "B", onClick: onClickB },
    ];
    render(<ButtonGroup items={groupItems} size="small" color="primary" variant="tabs" aria-label="test" />);

    const [first] = items();
    first.focus();
    pressKey(first, "ArrowRight");

    expect(onClickA).not.toHaveBeenCalled();
    expect(onClickB).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(items()[1]);
  });

  it("ArrowLeft wraps around and fires onClick exactly once", () => {
    const onClickA = vi.fn();
    const onClickB = vi.fn();
    const groupItems: ButtonGroupItemProps[] = [
      { label: "A", onClick: onClickA },
      { label: "B", onClick: onClickB },
    ];
    render(
      <ButtonGroup
        items={groupItems}
        size="small"
        color="primary"
        variant="radio"
        aria-label="test"
        defaultSelectedIndex={0}
      />,
    );

    const [first] = items();
    first.focus();
    pressKey(first, "ArrowLeft");

    expect(onClickB).toHaveBeenCalledTimes(1);
    expect(onClickA).not.toHaveBeenCalled();
  });

  it("mouse click fires the item's onClick exactly once and does not double-fire onSelectedIndexChange", () => {
    const onClick = vi.fn();
    const onSelectedIndexChange = vi.fn();
    const groupItems: ButtonGroupItemProps[] = [{ label: "A", onClick }, { label: "B" }];
    render(
      <ButtonGroup
        items={groupItems}
        size="small"
        color="primary"
        variant="tabs"
        aria-label="test"
        selectedIndex={1}
        onSelectedIndexChange={onSelectedIndexChange}
      />,
    );

    const [first] = items();
    act(() => {
      first.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onSelectedIndexChange).toHaveBeenCalledTimes(1);
    expect(onSelectedIndexChange).toHaveBeenCalledWith(0);
  });

  it("controlled onSelectedIndexChange fires exactly once on keyboard activation", () => {
    const onSelectedIndexChange = vi.fn();
    const groupItems: ButtonGroupItemProps[] = [{ label: "A" }, { label: "B" }];
    render(
      <ButtonGroup
        items={groupItems}
        size="small"
        color="primary"
        variant="tabs"
        aria-label="test"
        selectedIndex={0}
        onSelectedIndexChange={onSelectedIndexChange}
      />,
    );

    const [first] = items();
    first.focus();
    pressKey(first, "ArrowRight");

    expect(onSelectedIndexChange).toHaveBeenCalledTimes(1);
    expect(onSelectedIndexChange).toHaveBeenCalledWith(1);
  });

  it("skips disabled items on arrow navigation", () => {
    const onClickC = vi.fn();
    const groupItems: ButtonGroupItemProps[] = [
      { label: "A" },
      { label: "B", disabled: true },
      { label: "C", onClick: onClickC },
    ];
    render(<ButtonGroup items={groupItems} size="small" color="primary" variant="tabs" aria-label="test" />);

    const [first] = items();
    first.focus();
    pressKey(first, "ArrowRight");

    expect(document.activeElement).toBe(items()[2]);
    expect(onClickC).toHaveBeenCalledTimes(1);
  });

  it("Home focuses/selects the first enabled item and End focuses/selects the last enabled item", () => {
    const onClickB = vi.fn();
    const onClickC = vi.fn();
    const groupItems: ButtonGroupItemProps[] = [
      { label: "A", disabled: true },
      { label: "B", onClick: onClickB },
      { label: "C", onClick: onClickC },
      { label: "D", disabled: true },
    ];
    render(<ButtonGroup items={groupItems} size="small" color="primary" variant="tabs" aria-label="test" />);

    const [, second, , fourth] = items();
    fourth.focus();
    pressKey(fourth, "Home");
    expect(document.activeElement).toBe(second);
    expect(onClickB).toHaveBeenCalledTimes(1);

    second.focus();
    pressKey(second, "End");
    expect(document.activeElement).toBe(items()[2]);
    expect(onClickC).toHaveBeenCalledTimes(1);
  });

  it("does not move focus or selection when every item is disabled", () => {
    const groupItems: ButtonGroupItemProps[] = [
      { label: "A", disabled: true },
      { label: "B", disabled: true },
    ];
    render(<ButtonGroup items={groupItems} size="small" color="primary" variant="tabs" aria-label="test" />);

    const [first] = items();
    pressKey(first, "Home");
    pressKey(first, "End");
    pressKey(first, "ArrowRight");

    expect(document.activeElement).not.toBe(items()[1]);
  });

  it("exposes radiogroup/radio semantics for variant=radio", () => {
    const groupItems: ButtonGroupItemProps[] = [{ label: "A" }, { label: "B" }];
    render(
      <ButtonGroup
        items={groupItems}
        size="small"
        color="primary"
        variant="radio"
        aria-label="test"
        defaultSelectedIndex={0}
      />,
    );

    expect(container.querySelector('[role="radiogroup"]')).not.toBeNull();
    const [first, second] = items();
    expect(first.getAttribute("role")).toBe("radio");
    expect(first.getAttribute("aria-checked")).toBe("true");
    expect(second.getAttribute("aria-checked")).toBe("false");
    expect(first.getAttribute("aria-selected")).toBeNull();
  });

  it("exposes tablist/tab semantics for variant=tabs", () => {
    const groupItems: ButtonGroupItemProps[] = [{ label: "A" }, { label: "B" }];
    render(
      <ButtonGroup
        items={groupItems}
        size="small"
        color="primary"
        variant="tabs"
        aria-label="test"
        defaultSelectedIndex={1}
      />,
    );

    expect(container.querySelector('[role="tablist"]')).not.toBeNull();
    const [first, second] = items();
    expect(first.getAttribute("role")).toBe("tab");
    expect(second.getAttribute("aria-selected")).toBe("true");
    expect(first.getAttribute("aria-selected")).toBe("false");
    expect(first.getAttribute("aria-checked")).toBeNull();
  });
});
