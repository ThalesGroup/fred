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

// Keeps the running turn in view without pinning the reader to the bottom once
// the answer starts. Full autoscroll moves the line being read; none at all
// leaves the whole turn below the fold.
//
// Sole owner of the conversation container's scroll position — a second
// mechanism on the same element cannot be reasoned about.

import { useCallback, useEffect, useLayoutEffect, useRef, type RefObject } from "react";

/** How much of the viewport the answer may fill before the view stops moving. */
export const ANSWER_FOLLOW_FRACTION = 3 / 4;

/** Slack for "still at the bottom": sub-pixel rounding, and a hair of overscroll. */
export const NEAR_BOTTOM_PX = 48;

/** Share of the remaining distance covered per frame while following. */
export const FOLLOW_EASING = 0.22;

/** Under this, snap: easing toward a sub-pixel target never arrives. */
export const FOLLOW_SNAP_PX = 1;

/**
 * Next scroll position one frame closer to `target`.
 *
 * Exponential rather than a fixed step: the view catches up fast when a whole
 * tool row lands at once, and barely moves when a token adds a few pixels — so
 * the two do not read as different behaviours. The alternative, writing the
 * target outright on every content change, is what made this a series of small
 * jumps; native `behavior: "smooth"` is worse still, since each call restarts
 * its animation and there is one call per streamed batch.
 */
export function nextFollowTop(current: number, target: number): number {
  const remaining = target - current;
  if (Math.abs(remaining) <= FOLLOW_SNAP_PX) return target;
  return current + remaining * FOLLOW_EASING;
}

export type ScrollPhase = "idle" | "work" | "answer";

export interface ScrollIntentInput {
  phase: ScrollPhase;
  /** The view was at the bottom at the last scroll event — see `useChatAutoScroll`. */
  stuckToBottom: boolean;
  /** Content height now, and as it stood before the answer's first text. */
  scrollHeight: number;
  answerStartHeight: number | null;
  /** Visible height of the scroll container. */
  clientHeight: number;
}

/** True when the view is close enough to the bottom to count as following it. */
export function isNearBottom(scrollTop: number, scrollHeight: number, clientHeight: number): boolean {
  return scrollHeight - scrollTop - clientHeight <= NEAR_BOTTOM_PX;
}

/**
 * Whether the view is still following the bottom, after one scroll event.
 *
 * Neither distance nor direction decides this alone, because each has a case the
 * other covers.
 *
 * Distance alone is a race: the follow write and the browser's scroll event are
 * a frame apart, and content landing in between makes a perfectly-followed view
 * measure as far from the bottom — giving up for the rest of the turn with
 * nothing left to re-arm it. Hence: away from the bottom without having moved
 * up changes nothing.
 *
 * Direction alone misses content being REMOVED. Answering a HITL prompt takes
 * it out of the thread, so the page shortens and the browser clamps scrollTop
 * downward — no reader involved. Hence: at the bottom is following, whatever
 * moved the view there.
 */
export function resolveStuckToBottom(
  wasStuck: boolean,
  previousTop: number,
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
): boolean {
  if (isNearBottom(scrollTop, scrollHeight, clientHeight)) return true;
  if (scrollTop < previousTop - 1) return false;
  return wasStuck;
}

/**
 * Whether the view should be pushed to the bottom right now.
 *
 * The answer phase stops on its own without measuring any DOM node. The view is
 * at the bottom when the answer's first text lands, so the content grown since
 * the last trace-only height IS the answer's height on screen: following until
 * that exceeds ANSWER_FOLLOW_FRACTION of the viewport leaves the answer's first
 * line a quarter of the way down, reached gradually over its first lines rather
 * than in one jump.
 */
export function shouldFollowBottom({
  phase,
  stuckToBottom,
  scrollHeight,
  answerStartHeight,
  clientHeight,
}: ScrollIntentInput): boolean {
  if (phase === "idle") return false;
  // The reader scrolled away. Scrolling back re-arms it — during the work phase
  // that is the only way back, and it costs nothing to honour.
  if (!stuckToBottom) return false;
  if (phase === "work") return true;
  if (answerStartHeight === null) return true;
  return scrollHeight - answerStartHeight < clientHeight * ANSWER_FOLLOW_FRACTION;
}

export interface ChatAutoScrollInput {
  /**
   * Changes when the conversation is replaced or a new user turn starts — the
   * two moments the view jumps to the bottom outright. Must NOT change on
   * streaming tokens, or the answer would drag the viewport along.
   */
  turnKey: string;
  /** The turn is still running. */
  isStreaming: boolean;
  /** The turn has produced answer text, not just trace rows. */
  hasAnswerText: boolean;
  /** Trace rows so far this turn — a rise means the turn went back to work. */
  traceCount: number;
  /** A HITL gate is open: the turn is paused, not finished. */
  isAwaitingHuman: boolean;
}

/**
 * Drives the conversation's scroll container through a turn.
 *
 * Reads the container's own size rather than counting messages: trace rows,
 * tool rows and answer text all grow it, and the height is the only signal that
 * reflects what is actually on screen.
 */
export function useChatAutoScroll(
  containerRef: RefObject<HTMLDivElement | null>,
  { turnKey, isStreaming, hasAnswerText, traceCount, isAwaitingHuman }: ChatAutoScrollInput,
): void {
  // Whether the view was at the bottom at the last scroll event. Read from
  // scroll events rather than sniffed from wheel/touch/key gestures: those miss
  // scrollbar drags, keyboard scrolling and middle-click, and they fire for
  // nested scrollers (wide tables, code blocks) that never moved this view.
  // `scroll` does not bubble from an element, so only this container's own
  // movement is seen.
  const stuckToBottomRef = useRef(true);
  const previousTopRef = useRef(0);
  const answerStartHeightRef = useRef<number | null>(null);
  // Content height while the turn was still working. Sampled continuously so
  // the answer's budget is measured from the last trace-only height — taking it
  // when the answer phase begins would already include its first batch, and an
  // answer arriving in one chunk would leave a budget of zero.
  const workHeightRef = useRef<number | null>(null);
  const frameRef = useRef<number | null>(null);

  // A turn paused on a HITL gate is live, not finished: the prompt is the one
  // thing the reader has to act on, so it is followed into view like any other
  // work. Treating the pause as idle left them stranded above it, and the resume
  // then had nowhere to scroll back from.
  const live = isStreaming || isAwaitingHuman;
  const phase: ScrollPhase = !live ? "idle" : hasAnswerText && !isAwaitingHuman ? "answer" : "work";

  // Re-evaluated every frame, not only when content lands: the reader can take
  // over, and the answer can outgrow its budget, mid-animation. Sampling the
  // work height here keeps it current for the whole work phase.
  const evaluate = useCallback((): boolean => {
    const el = containerRef.current;
    if (!el) return false;

    if (phase === "work") workHeightRef.current = el.scrollHeight;
    if (phase === "answer" && answerStartHeightRef.current === null) {
      answerStartHeightRef.current = workHeightRef.current ?? el.scrollHeight;
    }

    return shouldFollowBottom({
      phase,
      stuckToBottom: stuckToBottomRef.current,
      scrollHeight: el.scrollHeight,
      answerStartHeight: answerStartHeightRef.current,
      clientHeight: el.clientHeight,
    });
  }, [containerRef, phase]);

  const follow = useCallback(() => {
    const el = containerRef.current;
    if (!el || !evaluate()) return;

    // Someone who asked the system for less motion gets the position, not the
    // journey.
    if (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.scrollTop = el.scrollHeight;
      return;
    }
    if (frameRef.current !== null || typeof requestAnimationFrame !== "function") {
      if (frameRef.current === null) el.scrollTop = el.scrollHeight;
      return;
    }

    const step = () => {
      frameRef.current = null;
      const node = containerRef.current;
      if (!node || !evaluate()) return;

      const target = node.scrollHeight - node.clientHeight;
      const next = nextFollowTop(node.scrollTop, target);
      node.scrollTop = next;
      // Settled: stop rather than burn a frame per token on a view already
      // where it belongs. The next content change starts it again.
      if (next !== target) frameRef.current = requestAnimationFrame(step);
    };
    frameRef.current = requestAnimationFrame(step);
  }, [containerRef, evaluate]);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      stuckToBottomRef.current = resolveStuckToBottom(
        stuckToBottomRef.current,
        previousTopRef.current,
        el.scrollTop,
        el.scrollHeight,
        el.clientHeight,
      );
      previousTopRef.current = el.scrollTop;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [containerRef]);

  // A tool round after the model has already written text puts the turn back to
  // work. `hasAnswerText` cannot say so — the answer text only accumulates — so
  // new trace rows drop the anchor and following resumes until the answer grows
  // again. Also covers a HITL resume, which adds no user message and so does not
  // change `turnKey`.
  useEffect(() => {
    answerStartHeightRef.current = null;
  }, [traceCount]);

  // Content changes come from streamed text, not from React commits alone — a
  // ResizeObserver on the scrolled content sees every one of them. The
  // container itself never changes size (it is a fixed flex child), so its
  // children are what has to be observed.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined" || typeof MutationObserver === "undefined") return;

    const resize = new ResizeObserver(() => follow());
    const pointAtContent = () => {
      resize.disconnect();
      for (const child of Array.from(el.children)) resize.observe(child);
    };
    pointAtContent();

    // The scrolled content is swapped wholesale when the thread replaces the
    // welcome screen or the session changes, which would leave the size
    // observer watching detached nodes.
    const mutation = new MutationObserver(pointAtContent);
    mutation.observe(el, { childList: true });

    return () => {
      resize.disconnect();
      mutation.disconnect();
    };
  }, [containerRef, follow]);

  // A new turn — or a conversation opening — lands at the bottom outright, with
  // no animation: the reader wants the end of the conversation, not its start.
  // Before paint, so the previous offset is never briefly shown.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Instant, and it wins: a new turn is not somewhere to ease towards.
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    answerStartHeightRef.current = null;
    workHeightRef.current = null;
    stuckToBottomRef.current = true;
    el.scrollTop = el.scrollHeight;
    previousTopRef.current = el.scrollTop;
  }, [containerRef, turnKey]);
}
