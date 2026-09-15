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

// The three behaviours that justify animating this by hand rather than through
// `scrollTo({ behavior: "smooth" })`: the target is re-read every frame, the
// reader can take the view back, and a starting turn cancels the animation.
// A native smooth scroll offers none of the three.

import { act, useRef, type RefObject } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useConversationJump } from "./useConversationJump";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
/** Pending frames by id, so cancellation can actually remove one — the whole
 *  point of animating by hand is that a frame can be called off. */
let frames: Map<number, FrameRequestCallback>;
let nextFrameId: number;

const CLIENT_HEIGHT = 500;
const SCROLL_HEIGHT = 5000;

/**
 * A scroll container holding one turn anchor whose distance from the top the
 * test controls — the stand-in for content above it changing height mid-flight.
 */
function makeScroller() {
  const el = document.createElement("div");
  const anchor = document.createElement("div");
  anchor.dataset.turnId = "u2";
  el.appendChild(anchor);

  let top = 0;
  /** The anchor's position in the scrolled content. */
  let anchorContentTop = 2000;
  Object.defineProperty(el, "clientHeight", { get: () => CLIENT_HEIGHT });
  Object.defineProperty(el, "scrollHeight", { get: () => SCROLL_HEIGHT });
  // When true, writes are silently dropped — the container that stops being
  // scrollable mid-flight.
  let immovable = false;
  Object.defineProperty(el, "scrollTop", {
    get: () => top,
    // happy-dom does not clamp on its own, and the clamp is load-bearing here:
    // the hook reads back what it wrote to tell a clamp from a reader takeover.
    set: (v: number) => {
      if (immovable) return;
      top = Math.max(0, Math.min(v, SCROLL_HEIGHT - CLIENT_HEIGHT));
    },
  });
  el.getBoundingClientRect = () => ({ top: 0 }) as DOMRect;
  // Viewport-relative, exactly as the real thing: content position minus scroll.
  anchor.getBoundingClientRect = () => ({ top: anchorContentTop - top }) as DOMRect;

  return {
    el,
    moveAnchorTo: (v: number) => (anchorContentTop = v),
    scrollTopOf: () => top,
    freezeScrolling: () => (immovable = true),
  };
}

function Probe({ el, isLive, onReady }: { el: HTMLDivElement; isLive: boolean; onReady: (j: Jump) => void }) {
  const ref = useRef<HTMLDivElement | null>(el) as RefObject<HTMLDivElement | null>;
  onReady(useConversationJump(ref, isLive));
  return null;
}

type Jump = (turnId: string) => void;

function render(el: HTMLDivElement, isLive: boolean): Jump {
  let jump!: Jump;
  act(() => {
    root.render(
      <Probe
        el={el}
        isLive={isLive}
        onReady={(j) => {
          jump = j;
        }}
      />,
    );
  });
  return jump;
}

/** Drain queued frames, letting the loop re-queue as it converges. */
function runFrames(n: number) {
  act(() => {
    for (let i = 0; i < n; i++) {
      const queued = [...frames.values()];
      frames.clear();
      for (const f of queued) f(i);
    }
  });
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  frames = new Map();
  nextFrameId = 1;
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    const id = nextFrameId++;
    frames.set(id, cb);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("useConversationJump", () => {
  it("eases towards the turn rather than landing in one step", () => {
    const { el, scrollTopOf } = makeScroller();
    const jump = render(el, false);
    act(() => jump("u2"));

    runFrames(1);
    const afterOne = scrollTopOf();
    // Target is 2000 - 16px of padding.
    expect(afterOne).toBeGreaterThan(0);
    expect(afterOne).toBeLessThan(1984);

    runFrames(60);
    expect(scrollTopOf()).toBe(1984);
  });

  it("follows the turn when content above it changes height mid-flight", () => {
    // The failure a native smooth scroll cannot avoid: it commits to a pixel
    // offset at call time, so a Mermaid block or image resolving above the
    // target lands the reader beside the wrong turn.
    const { el, moveAnchorTo, scrollTopOf } = makeScroller();
    const jump = render(el, false);
    act(() => jump("u2"));
    runFrames(2);

    moveAnchorTo(3000);
    runFrames(60);

    expect(scrollTopOf()).toBe(2984);
  });

  it("stops when the reader takes the view back", () => {
    const { el, scrollTopOf } = makeScroller();
    const jump = render(el, false);
    act(() => jump("u2"));
    runFrames(2);

    // The reader scrolls somewhere else entirely.
    act(() => {
      el.scrollTop = 100;
    });
    runFrames(60);

    expect(scrollTopOf()).toBe(100);
  });

  it("stops when a turn starts, leaving the autoscroll in charge", () => {
    const { el, scrollTopOf } = makeScroller();
    const jump = render(el, false);
    act(() => jump("u2"));
    runFrames(2);
    const whenTurnStarted = scrollTopOf();

    render(el, true);
    runFrames(60);

    expect(scrollTopOf()).toBe(whenTurnStarted);
  });

  it("lands immediately when the reader asked for reduced motion", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { el, scrollTopOf } = makeScroller();
    const jump = render(el, false);
    act(() => jump("u2"));

    expect(scrollTopOf()).toBe(1984);
    expect(frames.size).toBe(0);
  });

  it("suspends scroll anchoring for the flight, and restores it after", () => {
    // Anchoring silently adjusts scrollTop when content above the viewport
    // changes height — indistinguishable from the reader grabbing the
    // scrollbar, so it would abort the jump in the very case the hand-rolled
    // animation exists to survive.
    const { el } = makeScroller();
    const jump = render(el, false);
    act(() => jump("u2"));
    expect(el.style.overflowAnchor).toBe("none");

    runFrames(60);
    expect(el.style.overflowAnchor).toBe("");
  });

  it("gives up, and restores anchoring, when the container stops moving", () => {
    // It can stop being scrollable mid-flight — a side panel opening, the
    // conversation being replaced. Without a backstop the loop re-queues
    // forever against a target it can never reach, and scroll anchoring stays
    // suspended for the life of the page.
    const { el, freezeScrolling } = makeScroller();
    const jump = render(el, false);
    act(() => jump("u2"));
    runFrames(2);

    freezeScrolling();
    runFrames(300);

    expect(frames.size).toBe(0);
    expect(el.style.overflowAnchor).toBe("");
  });

  it("does nothing for a turn that is not in the thread", () => {
    const { el, scrollTopOf } = makeScroller();
    const jump = render(el, false);
    act(() => jump("nope"));
    runFrames(10);
    expect(scrollTopOf()).toBe(0);
  });
});
