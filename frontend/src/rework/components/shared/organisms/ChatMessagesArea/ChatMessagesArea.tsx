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

import { ReactNode, useEffect, useLayoutEffect, useRef } from "react";
import styles from "./ChatMessagesArea.module.css";

interface ChatMessagesAreaProps {
  children: ReactNode;
  isEmpty: boolean;
  isLoading: boolean;
  /** Bumped by parent whenever a new message is added — triggers the initial smooth scroll. */
  scrollVersion: number;
  /** True while the assistant is streaming — keeps the bottom pinned on every delta. */
  isStreaming: boolean;
}

// How close to the bottom (in px) re-enables tail mode after the user scrolls back down.
// Large enough to trigger even when streaming is adding content faster than the user
// can scroll — otherwise the "moving floor" prevents the threshold from ever firing.
const NEAR_BOTTOM_PX = 200;

export function ChatMessagesArea({ children, isEmpty, isLoading, scrollVersion, isStreaming }: ChatMessagesAreaProps) {
  const areaRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Tracks user scroll INTENT, not absolute scroll position.
  // Only scrolling UP (decreasing scrollTop) sets this to false.
  // Programmatic auto-scrolls go DOWN, so they never flip this flag.
  const isAtBottomRef = useRef(true);
  // Previous scrollTop — used to detect direction, not magnitude.
  const prevScrollTopRef = useRef(0);

  // Attach scroll listener once. Updates intent based on direction:
  //   scrolling UP   → user is reading history → disable auto-scroll
  //   scrolling DOWN → if near bottom, re-enable auto-scroll
  useEffect(() => {
    const scrollEl = areaRef.current?.parentElement;
    if (!scrollEl) return;

    function onScroll() {
      const { scrollTop, scrollHeight, clientHeight } = scrollEl!;
      const scrollingUp = scrollTop < prevScrollTopRef.current;
      prevScrollTopRef.current = scrollTop;

      if (scrollingUp) {
        isAtBottomRef.current = false;
      } else if (scrollHeight - scrollTop - clientHeight < NEAR_BOTTOM_PX) {
        // User scrolled back down to near the bottom — re-enable auto-scroll.
        isAtBottomRef.current = true;
      }
    }

    scrollEl.addEventListener("scroll", onScroll, { passive: true });
    return () => scrollEl.removeEventListener("scroll", onScroll);
  }, []);

  // New turn: always jump to bottom and declare intent "at bottom".
  // block:"end" — bottomRef lands at the viewport's bottom edge, preventing
  // the blank-space artifact when content is shorter than the viewport.
  useEffect(() => {
    isAtBottomRef.current = true;
    prevScrollTopRef.current = areaRef.current?.parentElement?.scrollTop ?? 0;
    bottomRef.current?.scrollIntoView({ behavior: "instant", block: "end" });
  }, [scrollVersion]);

  // Streaming ended: reset for the next exchange.
  useEffect(() => {
    if (!isStreaming) isAtBottomRef.current = true;
  }, [isStreaming]);

  // During streaming: follow the bottom only when the user hasn't scrolled up.
  // No dep array — runs after every render; no-op otherwise.
  useLayoutEffect(() => {
    if (!isStreaming || !isAtBottomRef.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "instant", block: "end" });
  });

  return (
    <div ref={areaRef} className={styles.area} role="log" aria-live="polite" aria-label="Conversation">
      <div className={styles.lane}>
        {isLoading && <p className={styles.hint}>Loading conversation history…</p>}
        {!isLoading && isEmpty && <p className={styles.empty}>Send a message to start the conversation.</p>}
        {children}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
