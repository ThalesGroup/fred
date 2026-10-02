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
import { afterEach, expect, it, vi } from "vitest";
import { Toast } from "./Toast";
import { ToastProvider, useToast } from "./ToastProvider";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
let container: HTMLDivElement;
function render(ui: React.ReactNode) {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(ui));
}
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

it("injects error copying and localizes action names without clipboard dependencies", async () => {
  const onCopy = vi.fn();
  const onClose = vi.fn();
  render(
    <Toast
      id={1}
      severity="error"
      summary="Failure"
      detail="Details"
      exiting={false}
      onCopy={onCopy}
      copyLabel="Copier"
      dismissLabel="Fermer"
      onClose={onClose}
      onExited={() => {}}
    />,
  );
  await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Copier"]')!.click());
  expect(onCopy).toHaveBeenCalledWith("Failure\nDetails");
  act(() => container.querySelector<HTMLButtonElement>('[aria-label="Fermer"]')!.click());
  expect(onClose).toHaveBeenCalledWith(1);
});

it("omits copy when the consumer supplies no action", () => {
  render(<Toast id={1} severity="error" summary="Failure" exiting={false} onClose={() => {}} onExited={() => {}} />);
  expect(container.querySelectorAll("button")).toHaveLength(1);
});

it("expires timed toasts and independently removes toasts created in the same turn", () => {
  vi.useFakeTimers();
  function Trigger() {
    const toast = useToast();
    return (
      <button
        onClick={() => {
          toast.showInfo({ summary: "First", duration: 100 });
          toast.showError({ summary: "Second" });
        }}
      >
        Notify
      </button>
    );
  }
  render(
    <ToastProvider>
      <Trigger />
    </ToastProvider>,
  );
  act(() => container.querySelector<HTMLButtonElement>("button")!.click());
  expect(container.querySelectorAll('[role="alert"]')).toHaveLength(2);
  act(() => vi.advanceTimersByTime(100));
  const first = container.querySelector<HTMLElement>('[role="alert"]')!;
  expect(first.className).toContain("toastExiting");
  act(() => first.dispatchEvent(new Event("animationend", { bubbles: true })));
  expect(container.querySelectorAll('[role="alert"]')).toHaveLength(1);
  expect(container.textContent).toContain("Second");
});

it.each([0, null, undefined])("handles duration %s without confusing zero with manual dismissal", (duration) => {
  vi.useFakeTimers();
  const onClose = vi.fn();
  render(
    <Toast
      id={7}
      severity="info"
      summary="Notice"
      duration={duration}
      exiting={false}
      onClose={onClose}
      onExited={() => {}}
    />,
  );
  expect(onClose).not.toHaveBeenCalled();
  act(() => vi.runAllTimers());
  if (duration === 0) expect(onClose).toHaveBeenCalledWith(7);
  else expect(onClose).not.toHaveBeenCalled();
});
