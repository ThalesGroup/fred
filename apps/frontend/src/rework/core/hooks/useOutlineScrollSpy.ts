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

/**
 * Fired when an anchor becomes, or stops being, wholly inside the container —
 * the `1` is what matters. The measurement below is "this turn's question has
 * reached the container's top edge", and an observer must actually fire at the
 * boundary being measured or the answer only refreshes by accident, whenever
 * some other anchor happens to cross an edge. `0` alone fires when an anchor
 * has fully left, which is a different line and up to one anchor-height late.
 */
const CROSSING_THRESHOLDS = [0, 1];

/**
 * The id of the turn the reader is currently in, or null.
 *
 * The active turn is the LAST anchor to have passed the container's top edge —
 * not the topmost anchor still on screen. The anchors sit on the user message
 * that opens each turn, so while the reader is partway through a long answer
 * there is no anchor on screen at all; "topmost visible" would blank the active
 * mark for exactly the turns the rail is most useful on.
 *
 * The observer is a trigger, not the measurement: it says an anchor crossed,
 * and the answer is then recomputed from the anchors' positions. Scrolling
 * between two distant anchors fires nothing, and correctly changes nothing. A
 * scroll handler would instead run on every one of the per-frame scroll writes
 * `useChatAutoScroll` makes while a turn streams.
 *
 * `sessionId` is in the subscription key, not decoration: two conversations can
 * hold the same number of turns, and re-keying on the count alone would leave
 * the observer watching the previous session's detached nodes. The autoscroll
 * guards the same case the same way.
 */
export function useOutlineScrollSpy(
  containerRef: RefObject<HTMLElement | null>,
  sessionId: string | null | undefined,
  turnCount: number,
): string | null {
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const root = containerRef.current;
    if (!root || turnCount === 0 || typeof IntersectionObserver === "undefined") {
      setActiveId(null);
      return;
    }

    const resolve = () => {
      const anchors = root.querySelectorAll<HTMLElement>("[data-turn-id]");
      if (anchors.length === 0) {
        setActiveId(null);
        return;
      }
      const line = root.getBoundingClientRect().top;
      let active: string | null = null;
      for (const anchor of anchors) {
        if (anchor.getBoundingClientRect().top > line) break;
        active = anchor.dataset.turnId ?? active;
      }
      // Above the first turn: it is still the one being read into.
      setActiveId(active ?? anchors[0].dataset.turnId ?? null);
    };

    const observer = new IntersectionObserver(resolve, { root, threshold: CROSSING_THRESHOLDS });
    for (const anchor of root.querySelectorAll("[data-turn-id]")) observer.observe(anchor);
    resolve();

    return () => observer.disconnect();
  }, [containerRef, sessionId, turnCount]);

  return activeId;
}
