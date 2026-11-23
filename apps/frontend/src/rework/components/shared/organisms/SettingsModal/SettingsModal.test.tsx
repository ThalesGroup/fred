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
import SettingsModal from "./SettingsModal";

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

  const render = (children: React.ReactNode) => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <SettingsModal isOpen onClose={() => undefined} id="settings" title="Settings">
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
});
