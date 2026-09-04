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

// The follow loop's React wiring, which the pure-function tests cannot reach.
// It has broken twice: once because the loop kept the `evaluate` it started
// with — so a loop begun in the work phase went on deciding as if the turn were
// still working, and the answer's freeze never came.

import { act, useRef, type RefObject } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChatAutoScroll, type ChatAutoScrollInput } from "./useChatAutoScroll";

let container: HTMLDivElement;
let root: Root;
/** Pending animation frames, drained by `runFrames`. */
let frames: FrameRequestCallback[];
/** Live size observers — content growth is announced through the observing ones. */
let observers: { cb: () => void; observing: boolean }[];

/** A scroll container whose geometry the test drives directly. */
function makeScroller(clientHeight: number) {
  const el = document.createElement("div");
  // The hook observes the container's CHILDREN — the container is a fixed flex
  // child and never changes size itself — so there has to be one.
  el.appendChild(document.createElement("div"));
  let scrollHeight = clientHeight;
  Object.defineProperty(el, "clientHeight", { get: () => clientHeight });
  Object.defineProperty(el, "scrollHeight", { get: () => scrollHeight });
  // happy-dom does not clamp scrollTop on its own.
  let top = 0;
  Object.defineProperty(el, "scrollTop", {
    get: () => top,
    set: (v: number) => {
      top = Math.max(0, Math.min(v, scrollHeight - clientHeight));
    },
  });
  // Growing content is what the hook reacts to, and it hears about it through
  // its ResizeObserver — nothing else calls follow().
  const grow = (px: number) => {
    scrollHeight += px;
    for (const o of observers) if (o.observing) o.cb();
  };
  return { el, grow };
}

function Probe({ el, input }: { el: HTMLDivElement; input: ChatAutoScrollInput }) {
  const ref = useRef<HTMLDivElement | null>(el) as RefObject<HTMLDivElement | null>;
  useChatAutoScroll(ref, input);
  return null;
}

const render = (el: HTMLDivElement, input: ChatAutoScrollInput) =>
  act(() => {
    root.render(<Probe el={el} input={input} />);
  });

/** Drain queued frames, letting the loop re-queue as it converges. */
function runFrames(n: number) {
  act(() => {
    for (let i = 0; i < n; i++) {
      const queued = frames;
      frames = [];
      for (const f of queued) f(i);
    }
  });
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  frames = [];
  observers = [];
  // Modelled with real semantics, because both matter here. `disconnect` must
  // stop the callback — the hook rebuilds its observer when the phase changes,
  // and a fake that kept firing the old one would run the previous phase's
  // logic, the very thing under test. But `disconnect` must NOT be permanent:
  // the hook calls it before re-pointing at the content, and an observer that
  // could not come back would go silent from the first render.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      private readonly entry: { cb: () => void; observing: boolean };
      constructor(cb: () => void) {
        this.entry = { cb, observing: false };
        observers.push(this.entry);
      }
      observe() {
        this.entry.observing = true;
      }
      disconnect() {
        this.entry.observing = false;
      }
    },
  );
  vi.stubGlobal(
    "MutationObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    frames.push(cb);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
  // Not stubbed by happy-dom; the hook reads it for prefers-reduced-motion.
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const input = (overrides: Partial<ChatAutoScrollInput> = {}): ChatAutoScrollInput => ({
  turnKey: "s1:1",
  isStreaming: true,
  hasAnswerText: false,
  traceCount: 0,
  isAwaitingHuman: false,
  ...overrides,
});

describe("useChatAutoScroll follow loop", () => {
  it("follows the bottom while the turn is working", () => {
    const { el, grow } = makeScroller(600);
    render(el, input());

    act(() => grow(400));
    runFrames(60);

    expect(el.scrollTop).toBe(400);
  });

  // The regression: the loop is started in the work phase and never settles,
  // because content keeps arriving. It must still notice the phase changed.
  it("freezes at the answer's share even though the loop began while working", () => {
    const { el, grow } = makeScroller(600);
    render(el, input());

    // Work phase: 400px of trace. Only one frame is run, so the loop is still
    // IN FLIGHT when the phase changes — letting it settle first would end it,
    // and the next growth would start a fresh one that never had the chance to
    // go stale. Content keeps arriving in a real turn, so the loop keeps
    // running across the phase change; that is the condition being tested.
    act(() => grow(400));
    runFrames(1);
    expect(el.scrollTop).toBeGreaterThan(0);
    expect(el.scrollTop).toBeLessThan(400);

    // The answer streams in a few pixels at a time, as real text does — growing
    // it in one block would blow the budget before the view had moved at all,
    // which proves nothing about the loop.
    const answerTop = 1000;
    render(el, input({ hasAnswerText: true }));
    for (let i = 0; i < 60; i++) {
      act(() => grow(10));
      runFrames(3);
    }

    // Frozen partway, not riding the answer to the bottom (2000 - 600 = 1400).
    expect(el.scrollTop).toBeLessThan(1400);
    // And frozen where it was asked to: the answer's first line about a quarter
    // of the way down, the viewport being 600 tall. The slack is the growth
    // step — the freeze lands on whichever increment crosses the threshold, it
    // does not split one.
    const answerTopOnScreen = answerTop - el.scrollTop;
    expect(answerTopOnScreen).toBeGreaterThan(600 / 4 - 20);
    expect(answerTopOnScreen).toBeLessThan(600 / 4 + 20);
  });
});
