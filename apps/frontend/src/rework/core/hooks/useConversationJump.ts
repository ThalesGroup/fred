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

// Animated jump to one turn, for the outline rail.
//
// Only ever runs while `useChatAutoScroll` is idle — see its ownership note.

import { useCallback, useEffect, useRef, type RefObject } from "react";
import { nextFollowTop } from "./useChatAutoScroll";

/** Breathing room left above the turn being jumped to, so it doesn't land
 *  flush against the container's masked top edge. Matches `--spacing-m`. */
const JUMP_TOP_PADDING_PX = 16;

/** Tolerance for "the container is where we left it". Scroll positions are
 *  fractional on scaled displays, so an exact comparison would read every
 *  frame as an interruption. */
const TAKEOVER_TOLERANCE_PX = 2;

/**
 * Hard ceiling on a jump's frames.
 *
 * `nextFollowTop` closes 22% of the remaining distance per frame, so it
 * converges geometrically: even a jump across ten thousand pixels is inside the
 * snap distance in well under fifty frames. Four seconds is therefore far
 * beyond any legitimate jump, and it exists only to bound the case where the
 * container stops moving at all — it stops being scrollable mid-flight, or the
 * conversation is replaced under us. Without it the loop re-queues forever
 * against a target it can never reach, and scroll anchoring stays suspended for
 * the life of the page.
 */
const MAX_JUMP_FRAMES = 240;

/**
 * Returns a `jumpTo(turnId)` that eases the conversation to that turn.
 *
 * Animated frame by frame rather than through `scrollTo({ behavior: "smooth" })`,
 * for three reasons that all bite in this container:
 *
 * - **The target is re-resolved every frame.** A native smooth scroll commits
 *   to a pixel offset at call time; anything above the target that changes
 *   height mid-flight (an image finishing, a Mermaid block rendering) then
 *   lands the reader beside the wrong turn. Reading the node's position each
 *   frame makes drift structurally impossible.
 * - **It can be cancelled.** A native smooth scroll cannot: the only way to
 *   stop one is an engine-dependent trick. A new turn starting has to be able
 *   to take the view back.
 * - **A reader taking over is detectable.** Comparing the container against
 *   the position we last wrote separates our own movement from theirs, which
 *   scroll events alone cannot do. Fighting the reader for the scroll position
 *   is the same failure the autoscroll's single-owner rule exists to prevent.
 *
 * Reuses `nextFollowTop` so a jump and the autoscroll's follow share one curve
 * and don't read as two different behaviours.
 */
export function useConversationJump(
  containerRef: RefObject<HTMLElement | null>,
  isLive: boolean,
): (turnId: string) => void {
  const frameRef = useRef<number | null>(null);
  // What we last wrote, to tell our own movement from the reader's.
  const writtenTopRef = useRef<number | null>(null);
  const framesLeftRef = useRef(0);

  const cancel = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    writtenTopRef.current = null;
    framesLeftRef.current = 0;
    // Scroll anchoring goes back on the moment we stop driving — see jumpTo.
    if (containerRef.current) containerRef.current.style.overflowAnchor = "";
  }, [containerRef]);

  useEffect(() => cancel, [cancel]);

  // A turn starting takes the view back: `useChatAutoScroll` jumps to the
  // bottom for it, and an animation still in flight would drag it away again.
  useEffect(() => {
    if (isLive) cancel();
  }, [isLive, cancel]);

  return useCallback(
    (turnId: string) => {
      const el = containerRef.current;
      if (!el) return;
      cancel();

      const targetTop = () => {
        const node = el.querySelector<HTMLElement>(`[data-turn-id="${CSS.escape(turnId)}"]`);
        if (!node) return null;
        const offset = node.getBoundingClientRect().top - el.getBoundingClientRect().top;
        const wanted = el.scrollTop + offset - JUMP_TOP_PADDING_PX;
        return Math.max(0, Math.min(wanted, el.scrollHeight - el.clientHeight));
      };

      const settle = () => {
        const target = targetTop();
        if (target !== null) el.scrollTop = target;
      };

      const reduced = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduced || typeof requestAnimationFrame !== "function") {
        settle();
        return;
      }

      // Suspend the browser's scroll anchoring for the flight. When content
      // above the viewport changes height, anchoring silently adjusts scrollTop
      // to hold the visual position — which the takeover check below cannot
      // tell from the reader grabbing the scrollbar, so the jump would abort in
      // exactly the mid-flight case it exists to survive. Re-resolving the
      // target every frame already does anchoring's job here.
      el.style.overflowAnchor = "none";

      const step = () => {
        frameRef.current = null;
        const node = containerRef.current;
        if (!node) return;
        // Someone else moved the view — the reader, or the autoscroll taking a
        // new turn back. Their position wins; we stop.
        if (
          writtenTopRef.current !== null &&
          Math.abs(node.scrollTop - writtenTopRef.current) > TAKEOVER_TOLERANCE_PX
        ) {
          cancel();
          return;
        }
        const target = targetTop();
        if (target === null) {
          cancel();
          return;
        }
        const next = nextFollowTop(node.scrollTop, target);
        node.scrollTop = next;
        // Read back rather than trusting the write: the browser clamps at the
        // ends, and an unread clamp would look exactly like a reader takeover
        // on the next frame.
        writtenTopRef.current = node.scrollTop;
        if (next === target || --framesLeftRef.current <= 0) {
          cancel();
          return;
        }
        frameRef.current = requestAnimationFrame(step);
      };
      framesLeftRef.current = MAX_JUMP_FRAMES;
      frameRef.current = requestAnimationFrame(step);
    },
    [containerRef, cancel],
  );
}
