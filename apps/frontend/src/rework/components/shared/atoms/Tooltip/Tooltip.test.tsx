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

// Coverage: the tooltip content portals onto document.body instead of
// rendering as a descendant of its trigger, so an ancestor's
// `overflow: hidden`/`scroll` (e.g. DataTable's scroll body) can never clip
// it — this is the regression a trigger near the top of such a container hit
// (the content popped upward with nowhere to go and got cut to an
// unreadable sliver). Also covers show/hide on hover and focus, and that it
// isn't rendered at all beforehand (nothing to clip when not shown).
//
// React delegates onMouseEnter/onMouseLeave/onFocus/onBlur from the
// non-bubbling native events (mouseenter/mouseleave/focus/blur) onto
// bubbling ones (mouseover/mouseout/focusin/focusout) dispatched at the
// root — so tests drive those, not the non-bubbling events the JSX prop
// names suggest.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Tooltip } from "./Tooltip";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function renderTooltip() {
  act(() => {
    root.render(
      <Tooltip text="Preview">
        <button>Trigger</button>
      </Tooltip>,
    );
  });
  return container.querySelector("button") as HTMLButtonElement;
}

describe("Tooltip", () => {
  it("does not render the tooltip content until hovered", () => {
    renderTooltip();
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });

  it("portals the tooltip content onto document.body, outside the trigger's own subtree", () => {
    const trigger = renderTooltip();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    const tooltip = document.querySelector('[role="tooltip"]');
    expect(tooltip).not.toBeNull();
    expect(container.contains(tooltip)).toBe(false);
    expect(document.body.contains(tooltip)).toBe(true);
  });

  it("hides the tooltip again on mouse leave", () => {
    const trigger = renderTooltip();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
    });
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });

  it("shows the tooltip on keyboard focus (Tab navigation) and links it via aria-describedby", () => {
    const trigger = renderTooltip();
    act(() => {
      // Real Tab navigation always fires a keydown before the resulting focus.
      trigger.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Tab" }));
      trigger.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    });
    const tooltip = document.querySelector('[role="tooltip"]');
    expect(tooltip).not.toBeNull();
    expect(trigger.getAttribute("aria-describedby")).toBe(tooltip?.id);
  });

  it("hides the tooltip on blur", () => {
    const trigger = renderTooltip();
    act(() => {
      trigger.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Tab" }));
      trigger.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    act(() => {
      trigger.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });

  it("does not show the tooltip for the lingering focus a mouse click leaves behind", () => {
    const trigger = renderTooltip();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      trigger.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });
});
