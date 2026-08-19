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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

  it("keeps the tooltip visible on mouse leave while keyboard focus remains", () => {
    const trigger = renderTooltip();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      trigger.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Tab" }));
      trigger.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
    });
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    act(() => {
      trigger.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });

  it("keeps the tooltip visible on blur while still hovered", () => {
    const trigger = renderTooltip();
    act(() => {
      trigger.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Tab" }));
      trigger.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    act(() => {
      trigger.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
    });
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });

  // Regression (#2384): a rich content panel opening BELOW its trigger used to
  // be placed at `trigger.bottom + gap` with no lower bound, so a trigger near
  // the top of the page — which has no room above either — rendered the panel
  // past the viewport's bottom edge, its internal scrollbar out of reach.
  it("keeps a panel that opens below fully inside the viewport", () => {
    Object.defineProperty(document.documentElement, "clientHeight", { value: 400, configurable: true });
    Object.defineProperty(document.documentElement, "clientWidth", { value: 1000, configurable: true });

    act(() => {
      root.render(
        <Tooltip content={<div>A long failure detail</div>}>
          <button>Trigger</button>
        </Tooltip>,
      );
    });
    // The WRAPPER span is what Tooltip measures, not the child.
    const wrapper = container.firstElementChild as HTMLElement;
    // No room above for a 300px panel, and not enough left below it either —
    // the squeeze a trigger high on a long page lands in.
    wrapper.getBoundingClientRect = () =>
      ({ top: 130, bottom: 150, left: 40, right: 100, width: 60, height: 20 }) as DOMRect;
    const trigger = container.querySelector("button") as HTMLButtonElement;

    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    const panel = document.querySelector('[role="tooltip"]') as HTMLElement;
    panel.getBoundingClientRect = () => ({ width: 200, height: 300 }) as DOMRect;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    // Unclamped this would sit at 154, putting its bottom edge at 454 in a
    // 400px viewport.
    expect(parseFloat(panel.style.top)).toBeLessThanOrEqual(400 - 4 - 300);
    expect(parseFloat(panel.style.top)).toBeGreaterThanOrEqual(4);
  });

  it("stays open while the pointer moves into an interactive panel", () => {
    vi.useFakeTimers();
    try {
      act(() => {
        root.render(
          <Tooltip interactive content={<button>Copy</button>}>
            <button>Trigger</button>
          </Tooltip>,
        );
      });
      const trigger = container.querySelector("button") as HTMLButtonElement;
      act(() => {
        trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      });
      const panel = document.querySelector('[role="tooltip"]') as HTMLElement;
      expect(panel).not.toBeNull();

      // Leaving the trigger *for the panel* must not dismiss it — otherwise the
      // copy button inside could never be reached, which is the whole point of
      // the interactive mode.
      act(() => {
        trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: panel }));
        panel.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
        vi.advanceTimersByTime(1000);
      });
      expect(document.querySelector('[role="tooltip"]')).not.toBeNull();

      // Leaving the panel itself does close it, after the grace delay.
      act(() => {
        panel.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
        vi.advanceTimersByTime(1000);
      });
      expect(document.querySelector('[role="tooltip"]')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("still dismisses immediately when it is not interactive", () => {
    // The default stays a plain hint: no lingering, no swallowed clicks.
    const trigger = renderTooltip();
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
    });
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });

  it("caps a panel taller than the screen instead of letting it spill", () => {
    // Clamping `top` cannot save a panel bigger than the viewport — it would
    // spill past whichever edge it was pushed toward. The cap is what makes the
    // clamp always solvable.
    Object.defineProperty(document.documentElement, "clientHeight", { value: 400, configurable: true });
    Object.defineProperty(document.documentElement, "clientWidth", { value: 300, configurable: true });

    act(() => {
      root.render(
        <Tooltip content={<div>Very long detail</div>}>
          <button>Trigger</button>
        </Tooltip>,
      );
    });
    const wrapper = container.firstElementChild as HTMLElement;
    wrapper.getBoundingClientRect = () =>
      ({ top: 200, bottom: 220, left: 150, right: 200, width: 50, height: 20 }) as DOMRect;
    const trigger = container.querySelector("button") as HTMLButtonElement;
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    const panel = document.querySelector('[role="tooltip"]') as HTMLElement;
    panel.getBoundingClientRect = () => ({ width: 900, height: 900 }) as DOMRect;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    expect(parseFloat(panel.style.maxHeight)).toBe(400 - 8);
    expect(parseFloat(panel.style.maxWidth)).toBe(300 - 8);
    // A panel as wide as the viewport can only sit at the margin.
    expect(parseFloat(panel.style.left)).toBe(4);
  });

  it("anchors by the top edge even when opening above, so a bad measurement cannot clip it", () => {
    // Regression (#2384, found live): the panel used to be placed by its BOTTOM
    // edge via translateY(-100%). A height measured smaller than what finally
    // rendered then grew the panel upward, past the top of the window, with its
    // title and first lines unreachable. Anchoring the top makes `top >= margin`
    // structural rather than a consequence of measuring correctly.
    Object.defineProperty(document.documentElement, "clientHeight", { value: 400, configurable: true });
    Object.defineProperty(document.documentElement, "clientWidth", { value: 1000, configurable: true });

    act(() => {
      root.render(
        <Tooltip content={<div>Detail</div>}>
          <button>Trigger</button>
        </Tooltip>,
      );
    });
    const wrapper = container.firstElementChild as HTMLElement;
    // Room above for a 300px panel, so it opens upward.
    wrapper.getBoundingClientRect = () =>
      ({ top: 350, bottom: 370, left: 400, right: 460, width: 60, height: 20 }) as DOMRect;
    const trigger = container.querySelector("button") as HTMLButtonElement;
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    const panel = document.querySelector('[role="tooltip"]') as HTMLElement;
    panel.getBoundingClientRect = () => ({ width: 200, height: 300 }) as DOMRect;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    // Both coordinates are the panel's own edges: no transform to reason about.
    expect(parseFloat(panel.style.top)).toBe(46);
    expect(panel.style.transform).toBe("");
    // Left-aligned with the trigger, so the panel visibly comes from it.
    expect(parseFloat(panel.style.left)).toBe(400);
  });

  it("keeps a panel too tall to sit above fully on screen", () => {
    Object.defineProperty(document.documentElement, "clientHeight", { value: 400, configurable: true });
    Object.defineProperty(document.documentElement, "clientWidth", { value: 1000, configurable: true });

    act(() => {
      root.render(
        <Tooltip content={<div>Detail</div>}>
          <button>Trigger</button>
        </Tooltip>,
      );
    });
    const wrapper = container.firstElementChild as HTMLElement;
    wrapper.getBoundingClientRect = () =>
      ({ top: 350, bottom: 370, left: 400, right: 460, width: 60, height: 20 }) as DOMRect;
    const trigger = container.querySelector("button") as HTMLButtonElement;
    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    const panel = document.querySelector('[role="tooltip"]') as HTMLElement;
    panel.getBoundingClientRect = () => ({ width: 200, height: 380 }) as DOMRect;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    const top = parseFloat(panel.style.top);
    expect(top).toBeGreaterThanOrEqual(4);
    expect(top + 380).toBeLessThanOrEqual(400 - 4);
  });
});
