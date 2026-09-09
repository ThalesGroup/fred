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

// Coverage centres on the two invariants the rail's safety rests on: while a
// turn is live it accepts no input (so it can never write the conversation's
// scroll position while useChatAutoScroll owns it), and preview extracts are
// derived on hover only, never for every turn up front.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationOutlineRail } from "./ConversationOutlineRail";
import type { OutlinePreview } from "./outlineItems";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const TURN_IDS = ["u1", "u2", "u3"];

const preview = (id: string): OutlinePreview => ({ request: `q ${id}`, answer: `a ${id}` });

type Props = Parameters<typeof ConversationOutlineRail>[0];

function render(props: Partial<Props> = {}) {
  const onJump = vi.fn();
  const getPreview = vi.fn(preview);
  const merged: Props = { turnIds: TURN_IDS, activeId: null, frozen: false, onJump, getPreview, ...props };
  act(() => root.render(<ConversationOutlineRail {...merged} />));
  // The spies are returned as themselves, not through `merged`, so their mock
  // metadata survives the Props widening.
  return { onJump, getPreview };
}

const marks = () => Array.from(container.querySelectorAll<HTMLElement>("[data-mark-id]"));

describe("ConversationOutlineRail", () => {
  it("renders one mark per turn, in order", () => {
    render();
    expect(marks().map((m) => m.dataset.markId)).toEqual(["u1", "u2", "u3"]);
  });

  it("renders nothing when there are no turns", () => {
    render({ turnIds: [] });
    expect(container.firstChild).toBeNull();
  });

  it("does not let a click focus a mark", () => {
    // A focused mark that the next turn then disables is force-blurred by
    // Chromium, which silently scrollIntoView()s the conversation — a scroll
    // write on the frames useChatAutoScroll owns the position.
    render();
    const event = new MouseEvent("mousedown", { bubbles: true, cancelable: true });
    marks()[0].dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("jumps to the turn a mark belongs to", () => {
    const { onJump } = render();
    act(() => marks()[1].click());
    expect(onJump).toHaveBeenCalledWith("u2");
  });

  it("marks the active turn and only that one", () => {
    render({ activeId: "u2" });
    const active = marks().filter((m) => m.className.includes("markActive"));
    expect(active.map((m) => m.dataset.markId)).toEqual(["u2"]);
  });

  it("gives every mark the same class, so none is visually singled out", () => {
    // The rail says where the turns are and nothing about them; a mark that
    // varied by turn would make it a second thing to read.
    render();
    const shapes = new Set(marks().map((m) => m.className.replace(/\s*\S*markActive\S*/, "")));
    expect(shapes.size).toBe(1);
  });

  it("keeps the marks out of the tab order", () => {
    // They live in an aria-hidden subtree: reachable by keyboard but silent to
    // a screen reader is worse than not reachable at all.
    render();
    expect(marks().every((m) => m.tabIndex === -1)).toBe(true);
  });

  it("hides the whole rail from assistive technology", () => {
    render();
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull();
  });

  describe("while a turn is live", () => {
    it("takes no click, so no jump can reach the conversation", () => {
      // The safety invariant: useChatAutoScroll owns the scroll position while
      // a turn runs, and a jump landing then would be overwritten a frame
      // later. Enforced in the markup, not only by the rail's pointer-events,
      // so a stylesheet change cannot quietly re-enable it.
      const { onJump } = render({ frozen: true });
      act(() => marks()[1].click());
      expect(onJump).not.toHaveBeenCalled();
      expect(marks().every((m) => (m as HTMLButtonElement).disabled)).toBe(true);
    });

    it("still shows the marks, so the reader keeps their position", () => {
      render({ frozen: true, activeId: "u2" });
      expect(marks()).toHaveLength(3);
      expect(marks().filter((m) => m.className.includes("markActive"))).toHaveLength(1);
    });

    it("keeps every mark mounted across the freeze, rather than rebuilding them", () => {
      // Swapping each mark's wrapper on freeze remounted the whole rail at both
      // ends of every turn — hundreds of mount/unmount cycles on the frames the
      // stream starts and finishes.
      render();
      const before = marks();
      render({ frozen: true });
      expect(marks()[0]).toBe(before[0]);
      expect(marks()[2]).toBe(before[2]);
    });
  });

  describe("preview extraction", () => {
    it("computes nothing until a mark is actually hovered", () => {
      // The guarantee that matters for performance: rendering the rail over a
      // long conversation must not walk every turn's text.
      const { getPreview } = render();
      expect(getPreview).not.toHaveBeenCalled();
    });

    it("computes only the hovered turn's extract", () => {
      const { getPreview } = render();
      act(() => {
        marks()[2].dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      });
      expect(getPreview.mock.calls).toEqual([["u3"]]);
      expect(document.querySelector('[role="tooltip"]')?.textContent).toBe("q u3a u3");
    });
  });
});
