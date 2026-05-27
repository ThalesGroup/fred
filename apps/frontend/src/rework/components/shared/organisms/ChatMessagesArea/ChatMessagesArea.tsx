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

import { type ReactNode, type RefObject, useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ChatMessagesArea.module.css";

interface ChatMessagesAreaProps {
  children: ReactNode;
  isEmpty: boolean;
  isLoading: boolean;
  /** Explicit scroll container passed from ManagedChatPage — never use parentElement. */
  scrollContainerRef: RefObject<HTMLDivElement>;
  /**
   * Increments when a new user exchange starts. Resets tail mode and jumps to
   * bottom. Must NOT change on every streaming token — only on new turns.
   */
  turnKey: number;
  isStreaming: boolean;
}

const BOTTOM_THRESHOLD_PX = 120;

function distanceFromBottom(el: HTMLElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

export function ChatMessagesArea({
  children,
  isEmpty,
  isLoading,
  scrollContainerRef,
  turnKey,
  isStreaming,
}: ChatMessagesAreaProps) {
  const { t } = useTranslation();

  // true  → follow the bottom during streaming (tail -f behaviour)
  // false → user scrolled up to read history; stop moving the viewport
  const tailModeRef = useRef(true);
  const lastScrollTopRef = useRef(0);

  const scrollToBottomInstant = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    lastScrollTopRef.current = el.scrollTop;
  }, [scrollContainerRef]);

  // Attach scroll listener to the external container once.
  // Scrolling UP  → disable tail mode immediately.
  // Scrolling DOWN + near bottom → re-enable tail mode.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const onScroll = () => {
      const scrollingUp = el.scrollTop < lastScrollTopRef.current;
      lastScrollTopRef.current = el.scrollTop;

      if (scrollingUp) {
        tailModeRef.current = false;
        return;
      }

      if (distanceFromBottom(el) <= BOTTOM_THRESHOLD_PX) {
        tailModeRef.current = true;
      }
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [scrollContainerRef]);

  // New user turn → always reset tail mode and jump to bottom.
  // Deliberately NOT triggered by streaming tokens.
  useLayoutEffect(() => {
    tailModeRef.current = true;
    scrollToBottomInstant();
  }, [turnKey, scrollToBottomInstant]);

  // During streaming: follow the bottom on every render, but only when tail
  // mode is active (i.e. user hasn't scrolled up).
  // No dep array — intentionally runs after every render.
  useLayoutEffect(() => {
    if (!isStreaming || !tailModeRef.current) return;
    scrollToBottomInstant();
  });

  return (
    <div className={styles.area} role="log" aria-live="polite" aria-label={t("chatbot.conversationAriaLabel")}>
      <div className={styles.lane}>
        {isLoading && <p className={styles.hint}>{t("chatbot.loadingHistory")}</p>}
        {!isLoading && isEmpty && <p className={styles.empty}>{t("chatbot.startConversationHint")}</p>}
        {children}
      </div>
    </div>
  );
}
