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
import SettingsModal, { type SettingsModalProps } from "./SettingsModal";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

describe("SettingsModal focus", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const render = (children: React.ReactNode, props: Partial<SettingsModalProps> = {}) => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <SettingsModal isOpen onClose={() => undefined} id="settings" title="Settings" {...props}>
          {children}
        </SettingsModal>,
      );
    });
  };

  it("takes focus when opened without a user action", async () => {
    render(<input disabled aria-label="field" />);
    await act(nextFrame);
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog?.contains(document.activeElement)).toBe(true);
  });

  it("leaves the first control the handoff picked after a click", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    trigger.focus();
    render(<button type="button">first</button>);
    await act(nextFrame);
    await act(nextFrame);
    expect(document.activeElement?.textContent).toBe("first");
    trigger.remove();
  });

  it("keeps a field that focused itself", async () => {
    render(<input autoFocus aria-label="field" />);
    await act(nextFrame);
    expect(document.activeElement).toBe(document.querySelector('input[aria-label="field"]'));
  });
  const press = (target: HTMLElement, key: string, options: KeyboardEventInit = {}) => {
    const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...options });
    act(() => target.dispatchEvent(event));
    return event;
  };

  it("cycles Tab and Shift+Tab inside the surface, including from its initial focus", async () => {
    render(
      <>
        <button>First</button>
        <input aria-label="Field" />
        <button disabled>Disabled</button>
        <button hidden>Hidden</button>
      </>,
    );
    await act(nextFrame);
    const first = document.querySelector("button")!;
    const last = document.querySelector("input")!;
    press(document.activeElement as HTMLElement, "Tab", { shiftKey: true });
    expect(document.activeElement).toBe(last);
    press(last, "Tab");
    expect(document.activeElement).toBe(first);
    press(first, "Tab", { shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("keeps focus on an empty surface when Tab is pressed", async () => {
    render(<input disabled />);
    await act(nextFrame);
    expect(press(document.activeElement as HTMLElement, "Tab").defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(document.querySelector('[role="dialog"]'));
  });

  it("submits a text field once and preserves Enter in other controls and composition", () => {
    const submit = vi.fn();
    render(
      <>
        <input />
        <textarea />
        <button>Cancel</button>
        <select>
          <option>A</option>
        </select>
      </>,
      { onSubmit: submit },
    );
    const input = document.querySelector("input")!;
    expect(press(input, "Enter").defaultPrevented).toBe(true);
    expect(submit).toHaveBeenCalledTimes(1);
    for (const target of document.querySelectorAll<HTMLElement>("textarea, button, select")) press(target, "Enter");
    press(input, "Enter", { shiftKey: true });
    press(input, "Enter", { isComposing: true });
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("does not submit while disabled or when a child consumes Enter", () => {
    const submit = vi.fn();
    render(<input onKeyDown={(event) => event.preventDefault()} />, { onSubmit: submit });
    press(document.querySelector("input")!, "Enter");
    expect(submit).not.toHaveBeenCalled();
    act(() =>
      root.render(
        <SettingsModal isOpen onClose={() => {}} id="settings" title="Settings" onSubmit={submit} submitDisabled>
          <input />
        </SettingsModal>,
      ),
    );
    press(document.querySelector("input")!, "Enter");
    expect(submit).not.toHaveBeenCalled();
  });
});
