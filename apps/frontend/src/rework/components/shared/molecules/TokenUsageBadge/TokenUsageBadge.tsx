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

import { useTranslation } from "react-i18next";
import type { TokenUsage } from "@rework/types/conversation";
import styles from "./TokenUsageBadge.module.css";

interface TokenUsageBadgeProps {
  usage: TokenUsage;
  /** "inline" (default): single row, used next to a message. "stacked": total on its
   *  own line above the in/out breakdown, used for conversation-level aggregates. */
  variant?: "inline" | "stacked";
}

export function TokenUsageBadge({ usage, variant = "inline" }: TokenUsageBadgeProps) {
  const { t } = useTranslation();

  const cached = usage.cache_read_tokens;

  const breakdown = (
    <>
      <span className={styles.segment}>↑{usage.input_tokens.toLocaleString()}</span>
      {!!cached && (
        <span className={styles.segment} title={t("chatbot.conversationTokenUsage.cached", { count: cached })}>
          ⚡{cached.toLocaleString()}
        </span>
      )}
      <span className={styles.sep}>·</span>
      <span className={styles.segment}>↓{usage.output_tokens.toLocaleString()}</span>
    </>
  );

  if (variant === "stacked") {
    return (
      <div className={`${styles.tokensUsage} ${styles.stacked}`}>
        <span className={styles.total}>{t("chatbot.conversationTokenUsage.total", { count: usage.total_tokens })}</span>
        <div className={styles.breakdownRow}>{breakdown}</div>
      </div>
    );
  }

  return (
    <div className={styles.tokensUsage}>
      {breakdown}
      <span className={styles.sep}>·</span>
      <span className={styles.total}>{usage.total_tokens.toLocaleString()} tokens</span>
    </div>
  );
}
