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

import { act, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useFocusHandoff } from "./useFocusHandoff";

function Harness({ open, autoFocus = false }: { open: boolean; autoFocus?: boolean }) {
  const surfaceRef = useRef<HTMLDivElement>(null);
  useFocusHandoff(open, surfaceRef);
  return (
    <>
      <button id="trigger">open</button>
      {open && (
        <div ref={surfaceRef}>
          <button id="first" autoFocus={autoFocus}>
            first
          </button>
          <button id="current" aria-current="page">
            current
          </button>
        </div>
      )}
      <button id="elsewhere">elsewhere</button>
      <textarea id="composer" />
    </>
  );
}

let container: HTMLDivElement;
let root: Root;
const render = (open: boolean, autoFocus = false) =>
  act(() => root.render(<Harness open={open} autoFocus={autoFocus} />));
const byId = (id: string) => container.querySelector<HTMLElement>(`#${id}`)!;
// A keyboard open: the key press precedes the surface opening.
const pressKey = () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  render(false);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("useFocusHandoff", () => {
  it("moves focus to the active item on open and back to the trigger on close", () => {
    byId("trigger").focus();
    pressKey();
    render(true);
    expect(document.activeElement).toBe(byId("current"));
    render(false);
    expect(document.activeElement).toBe(byId("trigger"));
  });

  it("leaves focus where the user moved it outside the surface", () => {
    byId("trigger").focus();
    pressKey();
    render(true);
    byId("elsewhere").focus();
    render(false);
    expect(document.activeElement).toBe(byId("elsewhere"));
  });

  it("does not take the caret from a field the user is typing in", () => {
    byId("composer").focus();
    pressKey();
    render(true);
    expect(document.activeElement).toBe(byId("composer"));
  });

  it("keeps the caret when a press on a control that does not take focus opens the surface", () => {
    byId("composer").focus();
    byId("trigger").dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    render(true);
    expect(document.activeElement).toBe(byId("composer"));
  });

  it("does not move focus when the surface opens with no recent user action", () => {
    byId("trigger").focus();
    vi.spyOn(performance, "now").mockReturnValue(performance.now() + 5000);
    render(true);
    expect(document.activeElement).toBe(byId("trigger"));
    vi.restoreAllMocks();
  });

  it("gives focus back to the pressed trigger when the surface autofocuses its own control", () => {
    byId("trigger").dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    render(true, true);
    expect(document.activeElement).toBe(byId("first"));
    render(false);
    expect(document.activeElement).toBe(byId("trigger"));
  });
});
