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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import IconButtonMenu from "./IconButtonMenu";

let container: HTMLDivElement;
let root: Root;
const onSelect = vi.fn();

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  onSelect.mockReset();
  act(() =>
    root.render(
      <IconButtonMenu
        iconButton={{
          variant: "icon",
          size: "medium",
          icon: { category: "outlined", type: "more_vert" },
          "aria-label": "Actions",
        }}
        options={[
          { value: "edit", key: "edit", label: "Edit" },
          { value: "off", key: "off", label: "Disabled", disabled: true },
          { value: "delete", key: "delete", label: "Delete" },
        ]}
        onSelect={onSelect}
      />,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const trigger = () => container.querySelector<HTMLButtonElement>('button[aria-label="Actions"]')!;
const listbox = () => document.querySelector<HTMLElement>('[role="listbox"]');
const key = (k: string) =>
  act(() => {
    document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true }));
  });

describe("IconButtonMenu", () => {
  it("moves focus into the list, skips disabled options and selects from the keyboard", () => {
    trigger().focus();
    key("Enter");
    act(() => trigger().click());
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(listbox());
    expect(listbox()?.getAttribute("aria-activedescendant")).toMatch(/opt-edit$/);
    key("ArrowDown");
    expect(listbox()?.getAttribute("aria-activedescendant")).toMatch(/opt-delete$/);
    key("Enter");
    expect(onSelect).toHaveBeenCalledWith("delete");
    expect(listbox()).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("gives focus back to the trigger on Escape", () => {
    trigger().focus();
    key("Enter");
    act(() => trigger().click());
    key("Escape");
    expect(listbox()).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("highlights nothing after a mouse open; ArrowUp then goes to the last option", () => {
    act(() => {
      trigger().dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
      trigger().click();
    });
    expect(listbox()?.hasAttribute("aria-activedescendant")).toBe(false);
    key("ArrowUp");
    expect(listbox()?.getAttribute("aria-activedescendant")).toMatch(/opt-delete$/);
  });
});
