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

// Which turn the reader is currently looking at, for the outline rail's active
// mark.

import { useEffect, useState, type RefObject } from "react";
import { isNearBottom } from "./useChatAutoScroll";

/** Where down the viewport a turn counts as the one being read. A turn becomes
 *  active once its question has climbed past this line, not when it merely
 *  peeks in from the bottom. */
const ACTIVE_LINE_RATIO = 0.35;

/**
 * The id of the turn the reader is currently in, or null.
 *
 * Two rules, and the second is not a special case — it is the common one:
 *
 * 1. **At the bottom, the last turn is active.** A short final turn never
 *    climbs past the reading line however far the reader scrolls: there simply
 *    isn't enough content below it to push it up there. Without this the rail
 *    would keep pointing at the previous turn while the reader sits on the
 *    newest one, which is where a conversation is read most of the time.
 * 2. Otherwise, the last turn whose question has passed the reading line. Not
 *    "the topmost anchor still on screen": the anchors sit on the user message
 *    that opens each turn, so partway through a long answer none is visible at
 *    all, and that rule would blank the mark on exactly the conversations the
 *    rail exists for.
 *
 * Driven by scroll rather than an IntersectionObserver. An observer only fires
 * when an element crosses a boundary, and rule 1 turns on the *scroll position*
 * — no anchor crosses anything over the last stretch to the bottom, so the
 * observer stays silent through precisely the case this has to get right.
 * A size observer covers what scrolling cannot: a side panel opening, a window
 * resize or a late-rendering diagram moves every anchor without a scroll event,
 * and the mark would otherwise stay wrong until the reader happened to scroll.
 *
 * `turnIds` must be identity-stable across renders (see ManagedChatPage) — it
 * is the subscription key, and it is the RIGHT key precisely because it is
 * derived from the messages: session id changes a render before the messages
 * do, so re-keying on that would resolve against the previous conversation and
 * then never correct itself.
 *
 * The cost that made an observer attractive is paid off differently: anchors
 * are in document order, so their positions are monotonic and the line is found
 * by binary search — around eight measurements for a two-hundred-turn
 * conversation, not two hundred. And nothing runs while a turn is live, which
 * is when `useChatAutoScroll` is writing the scroll position every frame.
 */
export function useOutlineScrollSpy(
  containerRef: RefObject<HTMLElement | null>,
  turnIds: string[],
  live: boolean,
): string | null {
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const root = containerRef.current;
    if (!root || turnIds.length === 0) {
      setActiveId(null);
      return;
    }

    const resolve = () => {
      const anchors = root.querySelectorAll<HTMLElement>("[data-turn-id]");
      if (anchors.length === 0) {
        setActiveId(null);
        return;
      }
      if (isNearBottom(root.scrollTop, root.scrollHeight, root.clientHeight)) {
        setActiveId(anchors[anchors.length - 1].dataset.turnId ?? null);
        return;
      }

      const line = root.getBoundingClientRect().top + root.clientHeight * ACTIVE_LINE_RATIO;
      let low = 0;
      let high = anchors.length - 1;
      let found = -1;
      while (low <= high) {
        const mid = (low + high) >> 1;
        if (anchors[mid].getBoundingClientRect().top <= line) {
          found = mid;
          low = mid + 1;
        } else {
          high = mid - 1;
        }
      }
      // Above the first turn: it is still the one being read into.
      const active = anchors[found === -1 ? 0 : found];
      setActiveId(active.dataset.turnId ?? null);
    };

    resolve();
    if (live) return;

    // Coalesced to one measurement per frame: a scroll event can fire more
    // often than the screen repaints, and re-measuring in between is work
    // nobody sees.
    let frame: number | null = null;
    const onScroll = () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        resolve();
      });
    };
    root.addEventListener("scroll", onScroll, { passive: true });

    // The container's own box and the content inside it both move the anchors.
    const sizes = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(onScroll);
    sizes?.observe(root);
    if (root.firstElementChild) sizes?.observe(root.firstElementChild);

    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      root.removeEventListener("scroll", onScroll);
      sizes?.disconnect();
    };
  }, [containerRef, turnIds, live]);

  return activeId;
}
