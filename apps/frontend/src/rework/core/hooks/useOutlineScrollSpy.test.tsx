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

// Two rules, and the reported bug was the absence of the first: a short final
// turn never climbs to any reading line, so sitting at the bottom of the
// conversation left the rail pointing at the turn before it.

import { act, useRef, type RefObject } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useOutlineScrollSpy } from "./useOutlineScrollSpy";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
let frames: FrameRequestCallback[];

const CLIENT_HEIGHT = 1000;
/** Reading line at 35% of the viewport: 350px below the container's top. */
const LINE = 350;

/**
 * A container whose anchor positions and scroll geometry the test drives.
 * `tops` and `geometry` stay live, so a test can move the content and fire a
 * scroll the way the browser would.
 */
function makeScroller(tops: Record<string, number>, geometry = { scrollTop: 0, scrollHeight: 10000 }) {
  const el = document.createElement("div");
  el.getBoundingClientRect = () => ({ top: 0 }) as DOMRect;
  Object.defineProperty(el, "clientHeight", { get: () => CLIENT_HEIGHT });
  Object.defineProperty(el, "scrollHeight", { get: () => geometry.scrollHeight });
  Object.defineProperty(el, "scrollTop", { get: () => geometry.scrollTop, set: () => {} });

  for (const id of Object.keys(tops)) {
    const anchor = document.createElement("div");
    anchor.dataset.turnId = id;
    anchor.getBoundingClientRect = () => ({ top: tops[id] }) as DOMRect;
    el.appendChild(anchor);
  }

  const scroll = () =>
    act(() => {
      el.dispatchEvent(new Event("scroll"));
      const queued = frames;
      frames = [];
      for (const f of queued) f(0);
    });
  return { el, tops, geometry, scroll, ids: Object.keys(tops) };
}

function Probe({
  el,
  ids,
  live,
  onValue,
}: {
  el: HTMLDivElement;
  ids: string[];
  live: boolean;
  onValue: (v: string | null) => void;
}) {
  const ref = useRef<HTMLDivElement | null>(el) as RefObject<HTMLDivElement | null>;
  onValue(useOutlineScrollSpy(ref, ids, live));
  return null;
}

/** `ids` is passed by reference, as ManagedChatPage does — the hook uses it as
 *  its subscription key, so a fresh array each render would re-subscribe
 *  endlessly. */
function render(scroller: { el: HTMLDivElement; ids: string[] }, live = false): () => string | null {
  let value: string | null = null;
  act(() => {
    root.render(
      <Probe
        el={scroller.el}
        ids={scroller.ids}
        live={live}
        onValue={(v) => {
          value = v;
        }}
      />,
    );
  });
  return () => value;
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => frames.push(cb));
  vi.stubGlobal("cancelAnimationFrame", () => {});
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("useOutlineScrollSpy", () => {
  it("marks the last turn active once the reader is at the bottom", () => {
    // The reported case: the final turn is short, so its question sits low on
    // screen and never reaches the reading line however far you scroll. Before
    // this rule the rail stayed on u1 while the reader sat on u2.
    const scroller = makeScroller({ u1: -2000, u2: 800 }, { scrollTop: 9000, scrollHeight: 10000 });
    expect(render(scroller)()).toBe("u2");
  });

  it("holds the last turn that passed the reading line", () => {
    // Partway through u2's long answer: u2's own anchor has scrolled out of
    // sight, and u3 is still below the line.
    const scroller = makeScroller({ u1: -3000, u2: -900, u3: 700 });
    expect(render(scroller)()).toBe("u2");
  });

  it("counts a turn as reached at the line, not at the very top of the screen", () => {
    // The criterion the report called too extreme: requiring the turn's start
    // to reach the top edge left it inactive through most of the screen.
    const scroller = makeScroller({ u1: -900, u2: LINE - 1 });
    expect(render(scroller)()).toBe("u2");
  });

  it("does not count a turn still below the line", () => {
    const scroller = makeScroller({ u1: -900, u2: LINE + 1 });
    expect(render(scroller)()).toBe("u1");
  });

  it("holds the first turn while the reader is still above it", () => {
    const scroller = makeScroller({ u1: 500, u2: 900 });
    expect(render(scroller)()).toBe("u1");
  });

  it("re-resolves as the reader scrolls", () => {
    const scroller = makeScroller({ u1: -900, u2: 800 });
    const { tops, scroll } = scroller;
    const active = render(scroller);
    expect(active()).toBe("u1");

    tops.u2 = 100;
    scroll();
    expect(active()).toBe("u2");
  });

  it("measures once per frame however many scroll events land", () => {
    const scroller = makeScroller({ u1: -900, u2: 800 });
    render(scroller);
    const { el } = scroller;

    act(() => {
      el.dispatchEvent(new Event("scroll"));
      el.dispatchEvent(new Event("scroll"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(frames).toHaveLength(1);
  });

  it("stops measuring while a turn is live", () => {
    // That is when useChatAutoScroll writes the scroll position every frame;
    // measuring on each of those writes is work nobody asked for.
    const scroller = makeScroller({ u1: -900, u2: 800 });
    const { tops, scroll } = scroller;
    const active = render(scroller, true);
    expect(active()).toBe("u1");

    tops.u2 = 100;
    scroll();
    expect(active()).toBe("u1");
  });

  it("reports nothing when the conversation has no turns", () => {
    expect(render(makeScroller({}))()).toBeNull();
  });
});
