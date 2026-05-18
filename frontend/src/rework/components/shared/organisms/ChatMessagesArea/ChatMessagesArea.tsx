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

// Pixels from the bottom within which we consider the user "at the bottom".
// Keeps auto-scroll active for small rounding differences without fighting the user.
const BOTTOM_THRESHOLD_PX = 120;

export function ChatMessagesArea({ children, isEmpty, isLoading, scrollVersion, isStreaming }: ChatMessagesAreaProps) {
  const areaRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Smooth jump when a new turn starts (message count changes).
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [scrollVersion]);

  // During streaming, pin the bottom only when the user is already near it.
  // If they have scrolled up to read history, this is a no-op — they stay put.
  // No dependency array — intentionally runs after every render, no-op when not streaming.
  useLayoutEffect(() => {
    if (!isStreaming) return;
    const scrollEl = areaRef.current?.parentElement;
    if (!scrollEl) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollEl;
    if (scrollHeight - scrollTop - clientHeight < BOTTOM_THRESHOLD_PX) {
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }
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
