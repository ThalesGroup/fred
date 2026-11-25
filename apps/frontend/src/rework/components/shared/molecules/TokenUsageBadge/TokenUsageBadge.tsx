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

import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useTranslation } from "react-i18next";
import type { TokenUsage } from "@rework/types/conversation";
import styles from "./TokenUsageBadge.module.css";

interface TokenUsageBadgeProps {
  usage: TokenUsage;
}

// Per-message badge: in and out, nothing else (#2403). The total was dropped
// as visual weight — it is the sum of the two figures already on the line, and
// the conversation total sits in the header.
export function TokenUsageBadge({ usage }: TokenUsageBadgeProps) {
  const { t, i18n } = useTranslation();

  const cached = usage.cache_read_tokens;
  // Grouped against the ACTIVE UI language, not the browser's — the header's
  // total goes through i18next's `number` formatter, which follows
  // `i18n.language`, so a bare `toLocaleString()` here would disagree with it
  // for anyone whose browser language differs from their Fred language.
  const n = (value: number) => value.toLocaleString(i18n.language);

  // The arrows alone don't say which direction is which, so each carries the
  // spelled-out figure on hover.
  return (
    <div className={styles.tokensUsage}>
      <Tooltip content={t("chatbot.conversationTokenUsage.sent", { count: usage.input_tokens })} asChild>
        <span tabIndex={0} className={styles.segment}>
          ↑{n(usage.input_tokens)}
        </span>
      </Tooltip>
      {!!cached && (
        <Tooltip content={t("chatbot.conversationTokenUsage.cached", { count: cached })} asChild>
          <span tabIndex={0} className={styles.segment}>
            ⚡{n(cached)}
          </span>
        </Tooltip>
      )}
      <span className={styles.sep}>·</span>
      <Tooltip content={t("chatbot.conversationTokenUsage.received", { count: usage.output_tokens })} asChild>
        <span tabIndex={0} className={styles.segment}>
          ↓{n(usage.output_tokens)}
        </span>
      </Tooltip>
    </div>
  );
}
