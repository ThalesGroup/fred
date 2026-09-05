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

import { describe, expect, it } from "vitest";
import {
  ANSWER_FOLLOW_FRACTION,
  NEAR_BOTTOM_PX,
  FOLLOW_EASING,
  FOLLOW_SNAP_PX,
  isNearBottom,
  nextFollowTop,
  resolveStuckToBottom,
  shouldFollowBottom,
  type ScrollIntentInput,
} from "./useChatAutoScroll";

const input = (overrides: Partial<ScrollIntentInput> = {}): ScrollIntentInput => ({
  phase: "work",
  stuckToBottom: true,
  scrollHeight: 1000,
  answerStartHeight: null,
  clientHeight: 600,
  ...overrides,
});

describe("shouldFollowBottom", () => {
  it("does nothing between turns", () => {
    expect(shouldFollowBottom(input({ phase: "idle" }))).toBe(false);
  });

  it("follows the bottom while the trace grows", () => {
    expect(shouldFollowBottom(input({ phase: "work" }))).toBe(true);
  });

  // The whole point: a reader who scrolls away keeps the view, in every phase.
  it("stops as soon as the reader has scrolled away from the bottom", () => {
    expect(shouldFollowBottom(input({ phase: "work", stuckToBottom: false }))).toBe(false);
    expect(shouldFollowBottom(input({ phase: "answer", stuckToBottom: false }))).toBe(false);
  });

  it("re-arms when the reader scrolls back down", () => {
    expect(shouldFollowBottom(input({ phase: "work", stuckToBottom: true }))).toBe(true);
  });

  describe("answer phase", () => {
    // 600px viewport at ANSWER_FOLLOW_FRACTION = 3/4, so the view follows for
    // the answer's first 450px and freezes after — leaving its first line a
    // quarter of the way down.
    const answerAfter = (grown: number) =>
      shouldFollowBottom(input({ phase: "answer", answerStartHeight: 1000, scrollHeight: 1000 + grown }));

    it("keeps following while the answer is shorter than its share of the viewport", () => {
      expect(answerAfter(0)).toBe(true);
      expect(answerAfter(449)).toBe(true);
    });

    it("freezes once the answer has filled that share", () => {
      expect(answerAfter(450)).toBe(false);
      expect(answerAfter(5000)).toBe(false);
    });

    it("follows until the anchor has been taken", () => {
      expect(shouldFollowBottom(input({ phase: "answer", answerStartHeight: null }))).toBe(true);
    });

    it("derives the stop from the declared fraction, not a hardcoded number", () => {
      const clientHeight = 900;
      const grown = clientHeight * ANSWER_FOLLOW_FRACTION;
      const at = (h: number) =>
        shouldFollowBottom(input({ phase: "answer", answerStartHeight: 0, scrollHeight: h, clientHeight }));
      expect(at(grown - 1)).toBe(true);
      expect(at(grown)).toBe(false);
    });
  });
});

describe("isNearBottom", () => {
  it("treats sub-pixel and small overscroll gaps as being at the bottom", () => {
    expect(isNearBottom(400, 1000, 600)).toBe(true);
    expect(isNearBottom(400 - NEAR_BOTTOM_PX, 1000, 600)).toBe(true);
  });

  it("reports a real scroll-up as away from the bottom", () => {
    expect(isNearBottom(400 - NEAR_BOTTOM_PX - 1, 1000, 600)).toBe(false);
  });
});

describe("resolveStuckToBottom", () => {
  // 1000 tall, 600 visible: the bottom is scrollTop 400.
  const at = (wasStuck: boolean, previousTop: number, top: number, height = 1000) =>
    resolveStuckToBottom(wasStuck, previousTop, top, height, 600);

  it("gives up following as soon as the reader moves up", () => {
    expect(at(true, 400, 300)).toBe(false);
  });

  it("re-arms when the reader comes back to the bottom", () => {
    expect(at(false, 300, 400)).toBe(true);
  });

  it("stays given up while the reader scrolls down but not to the bottom", () => {
    expect(at(false, 100, 200)).toBe(false);
  });

  // The race this function exists for: our own follow lands, and content that
  // arrived in the meantime leaves the view measuring far from the bottom.
  // Distance alone would give up here, with nothing left to re-arm it.
  it("keeps following when content outran the follow write", () => {
    expect(at(true, 400, 400, 2000)).toBe(true);
  });

  // Answering a HITL prompt removes it from the thread: the page shortens and
  // the browser clamps scrollTop downward with no reader involved. Direction
  // alone read that as a scroll-up and killed the resume's autoscroll.
  it("keeps following when removed content clamped the view downward", () => {
    // Page shrank 1000 -> 800, so the bottom moved from scrollTop 400 to 200.
    expect(at(true, 400, 200, 800)).toBe(true);
  });

  it("ignores a sub-pixel jitter upward", () => {
    expect(at(true, 400, 399.5)).toBe(true);
  });
});

describe("nextFollowTop", () => {
  it("covers a share of the remaining distance, not a fixed step", () => {
    expect(nextFollowTop(0, 1000)).toBeCloseTo(1000 * FOLLOW_EASING);
    expect(nextFollowTop(500, 1000)).toBeCloseTo(500 + 500 * FOLLOW_EASING);
  });

  // Otherwise the loop would run forever, a frame per token, on a view already
  // where it belongs.
  it("snaps to the target once within the snap distance", () => {
    expect(nextFollowTop(1000 - FOLLOW_SNAP_PX, 1000)).toBe(1000);
    expect(nextFollowTop(1000, 1000)).toBe(1000);
  });

  it("converges without overshooting", () => {
    let top = 0;
    for (let i = 0; i < 200; i++) top = nextFollowTop(top, 1000);
    expect(top).toBe(1000);
  });

  it("eases upward too, when removed content lowered the target", () => {
    expect(nextFollowTop(1000, 800)).toBeCloseTo(1000 - 200 * FOLLOW_EASING);
  });
});
