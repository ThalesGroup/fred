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

// The rule under test is "last anchor to have passed the reading line", not
// "topmost anchor still on screen". The anchors sit on the user message that
// opens each turn, so partway through a long answer no anchor is on screen at
// all — the naive rule blanks the active mark on exactly the conversations the
// rail exists for.

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
/** Fires every live observer — the hook uses it only as a "something crossed"
 *  trigger, then measures the anchors itself. */
let notifyObservers: () => void;
/** Options the hook handed its observer, and how many it has built. */
let observerOptions: IntersectionObserverInit | undefined;
let observerCount: number;

/** A container whose anchors sit at test-controlled distances from its top. */
function makeScroller(anchorTops: Record<string, number>) {
  const el = document.createElement("div");
  el.getBoundingClientRect = () => ({ top: 0 }) as DOMRect;
  const tops = { ...anchorTops };
  for (const id of Object.keys(tops)) {
    const anchor = document.createElement("div");
    anchor.dataset.turnId = id;
    anchor.getBoundingClientRect = () => ({ top: tops[id] }) as DOMRect;
    el.appendChild(anchor);
  }
  return { el, moveTo: (id: string, top: number) => (tops[id] = top) };
}

function Probe({
  el,
  sessionId,
  count,
  onValue,
}: {
  el: HTMLDivElement;
  sessionId: string;
  count: number;
  onValue: (v: string | null) => void;
}) {
  const ref = useRef<HTMLDivElement | null>(el) as RefObject<HTMLDivElement | null>;
  onValue(useOutlineScrollSpy(ref, sessionId, count));
  return null;
}

function render(el: HTMLDivElement, count: number, sessionId = "s1"): () => string | null {
  let value: string | null = null;
  act(() => {
    root.render(
      <Probe
        el={el}
        sessionId={sessionId}
        count={count}
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
  const callbacks: (() => void)[] = [];
  observerOptions = undefined;
  observerCount = 0;
  notifyObservers = () => act(() => callbacks.forEach((cb) => cb()));
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: () => void, options?: IntersectionObserverInit) {
        callbacks.push(cb);
        observerOptions = options;
        observerCount += 1;
      }
      observe() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("useOutlineScrollSpy", () => {
  it("holds the last turn that passed the reading line", () => {
    // u2 is above the top edge, u3 still well below it: the reader is inside
    // u2's answer even though u2's own anchor has scrolled out of sight.
    const { el } = makeScroller({ u1: -3000, u2: -900, u3: 700 });
    const active = render(el, 3);
    notifyObservers();
    expect(active()).toBe("u2");
  });

  it("moves on only once the next turn reaches the container's top edge", () => {
    const { el, moveTo } = makeScroller({ u1: -900, u2: 400 });
    const active = render(el, 2);
    notifyObservers();
    expect(active()).toBe("u1");

    // Peeking in from the bottom is not enough...
    moveTo("u2", 200);
    notifyObservers();
    expect(active()).toBe("u1");

    // ...crossing the top edge is. The measured line has to be a boundary the
    // observer actually fires on, or the answer would only ever refresh by
    // accident, when some unrelated anchor happened to cross an edge.
    moveTo("u2", -1);
    notifyObservers();
    expect(active()).toBe("u2");
  });

  it("observes the crossing the resolver measures", () => {
    const { el } = makeScroller({ u1: -100 });
    render(el, 1);
    // threshold 1 fires as an anchor stops being wholly inside the container,
    // which is the moment its top passes the edge — the line resolve() reads.
    expect(observerOptions?.threshold).toEqual([0, 1]);
  });

  it("re-subscribes when the session changes but the turn count does not", () => {
    // Two conversations can hold the same number of turns; keying on the count
    // alone left the observer on the previous session's detached nodes.
    const { el } = makeScroller({ u1: -100, u2: 500 });
    render(el, 2);
    const before = observerCount;
    render(el, 2, "s2");
    expect(observerCount).toBeGreaterThan(before);
  });

  it("holds the first turn while the reader is still above it", () => {
    const { el } = makeScroller({ u1: 300, u2: 900 });
    const active = render(el, 2);
    notifyObservers();
    expect(active()).toBe("u1");
  });

  it("reports nothing when the conversation has no turns", () => {
    const { el } = makeScroller({});
    expect(render(el, 0)()).toBeNull();
  });
});
