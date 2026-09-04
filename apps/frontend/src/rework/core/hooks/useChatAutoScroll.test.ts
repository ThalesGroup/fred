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
  isNearBottom,
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
    // 600px viewport, so the view follows for the answer's first 200px and
    // freezes after — leaving its first line two thirds of the way down.
    const answerAfter = (grown: number) =>
      shouldFollowBottom(input({ phase: "answer", answerStartHeight: 1000, scrollHeight: 1000 + grown }));

    it("keeps following while the answer is shorter than a third of the viewport", () => {
      expect(answerAfter(0)).toBe(true);
      expect(answerAfter(199)).toBe(true);
    });

    it("freezes once the answer has filled that third", () => {
      expect(answerAfter(200)).toBe(false);
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
