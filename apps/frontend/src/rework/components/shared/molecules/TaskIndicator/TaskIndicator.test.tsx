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

// React maps onMouseEnter/onFocus onto bubbling mouseover/focusin, so tests dispatch those.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const task = {
  taskId: "task-1",
  kind: "ingestion",
  state: "failed",
  progress: null,
  step: null,
  error: "boom",
  registeredAt: new Date().toISOString(),
  acknowledgedAt: null,
  localOnly: true,
  target: { label: "report.pdf" },
};

vi.mock("react-redux", () => ({ useSelector: () => task }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../features/tasks/useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge: vi.fn(), isAcknowledging: () => false }),
}));

import { TaskIndicator } from "./TaskIndicator";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const ACK = "rework.tasks.popover.acknowledge";
const hasAck = (el: Element | null) => [...(el?.querySelectorAll("button") ?? [])].some((b) => b.textContent === ACK);
const panel = () => document.querySelector<HTMLElement>('[role="tooltip"]');

describe("TaskIndicator", () => {
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
  });

  const render = (trigger?: "click" | "hover") => {
    act(() => root.render(<TaskIndicator taskId="task-1" trigger={trigger} />));
    return container.querySelector("button")!;
  };

  it("opens the detail with acknowledgement on click by default", () => {
    const button = render();
    act(() => button.click());
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(hasAck(dialog)).toBe(true);
  });

  describe("hover mode", () => {
    it("opens on hover without acknowledgement, and a click opens nothing else", () => {
      const button = render("hover");
      act(() => button.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
      expect(panel()?.textContent).toContain("boom");
      expect(hasAck(panel())).toBe(false);
      act(() => button.click());
      expect(document.querySelector('[role="dialog"]')).toBeNull();
    });

    it("stays open while the pointer crosses into the panel, closes once it leaves", () => {
      vi.useFakeTimers();
      const button = render("hover");
      act(() => button.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
      const surface = panel()!;
      act(() => {
        button.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: surface }));
        surface.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
        vi.advanceTimersByTime(1000);
      });
      expect(panel()).not.toBeNull();
      act(() => {
        surface.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
        vi.advanceTimersByTime(1000);
      });
      expect(panel()).toBeNull();
    });

    it("opens on keyboard focus without taking focus, closes on Escape and on blur", () => {
      const button = render("hover");
      const focusIn = () => {
        button.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Tab" }));
        button.focus();
        button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
      };
      act(focusIn);
      expect(panel()).not.toBeNull();
      expect(document.activeElement).toBe(button);
      act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
      expect(panel()).toBeNull();

      act(focusIn);
      expect(panel()).not.toBeNull();
      act(() => button.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
      expect(panel()).toBeNull();
    });
  });
});
