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

import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ChatMessagesArea.module.css";

interface ChatMessagesAreaProps {
  children: ReactNode;
  isEmpty: boolean;
  isLoading: boolean;
  emptyState?: ReactNode;
}

// Presentation only. Scrolling the container this renders into belongs to
// `useChatAutoScroll`, which also has to decide when NOT to move: two owners on
// one element cannot be reasoned about.
export function ChatMessagesArea({ children, isEmpty, isLoading, emptyState }: ChatMessagesAreaProps) {
  const { t } = useTranslation();

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
