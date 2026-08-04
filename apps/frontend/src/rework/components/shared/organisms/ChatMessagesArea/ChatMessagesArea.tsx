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

import { type ReactNode, type RefObject, useCallback, useLayoutEffect } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ChatMessagesArea.module.css";

interface ChatMessagesAreaProps {
  children: ReactNode;
  isEmpty: boolean;
  isLoading: boolean;
  emptyState?: ReactNode;
  /** Explicit scroll container passed from ManagedChatPage — never use parentElement. */
  scrollContainerRef: RefObject<HTMLDivElement>;
  /**
   * Increments when a new user exchange starts (including the initial mount,
   * e.g. when opening a session with history). Jumps to bottom once for that
   * turn. Must NOT change on every streaming token — while the agent writes
   * its response, the viewport must never move on its own; only the user's
   * own scrolling may move it.
   */
  turnKey: number;
}

export function ChatMessagesArea({
  children,
  isEmpty,
  isLoading,
  emptyState,
  scrollContainerRef,
  turnKey,
}: ChatMessagesAreaProps) {
  const { t } = useTranslation();

  const scrollToBottomInstant = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [scrollContainerRef]);

  // New user turn (or initial mount) → jump to bottom once. Deliberately not
  // re-run on streaming tokens — see turnKey doc above.
  useLayoutEffect(() => {
    scrollToBottomInstant();
  }, [turnKey, scrollToBottomInstant]);

  return (
    <div className={styles.area} role="log" aria-live="polite" aria-label={t("chatbot.conversationAriaLabel")}>
      <div className={styles.lane}>
        {isLoading && <p className={styles.hint}>{t("chatbot.loadingHistory")}</p>}
        {!isLoading && isEmpty && (emptyState ?? <p className={styles.empty}>{t("chatbot.startConversationHint")}</p>)}
        {children}
      </div>
    </div>
  );
}
