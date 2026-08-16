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
import styles from "./CharacterLimitNotice.module.css";

interface CharacterLimitNoticeProps {
  /** Id the described field points at with `aria-describedby`. */
  id: string;
  /** Code-point count of the exact value the field will submit. */
  count: number | undefined;
  /** Runtime-published code-point limit; nothing renders when the runtime publishes none. */
  limit: number | undefined;
  /** Extra class on the root — used to align the notice with a padded field. */
  className?: string;
}

/**
 * Over-limit notice for the chat composer and the HITL free-text prompt.
 *
 * Deliberately silent at rest: an ordinary message sits far below the limit, so
 * a counter that is always on screen reports a non-problem for the whole life
 * of the draft (issue #2358). Only the message and count are shown here — the
 * `aria-invalid` state and the send gating stay with the field that owns them.
 */
export function CharacterLimitNotice({ id, count, limit, className }: CharacterLimitNoticeProps) {
  const { t, i18n } = useTranslation();

  if (count === undefined || limit === undefined) return null;

  const isOver = count > limit;
  const formattedLimit = limit.toLocaleString(i18n.language);

  return (
    // The element stays mounted for the life of the field so the polite live
    // region is in the accessibility tree before the message appears — a live
    // region inserted at the same time as its text is not announced. While the
    // draft is within the limit it is empty and out of flow, so it costs no
    // space. The count is deliberately outside the live region: inside, it
    // would re-announce on every keystroke.
    <div id={id} className={`${styles.notice} ${isOver ? styles.visible : ""} ${className ?? ""}`}>
      <span aria-live="polite">{isOver ? t("chatbot.errors.chatInputTooLong", { limit: formattedLimit }) : ""}</span>
      {isOver && (
        <span className={styles.count}>
          {t("chatbot.characterCounter", {
            count,
            used: count.toLocaleString(i18n.language),
            limit: formattedLimit,
          })}
        </span>
      )}
    </div>
  );
}
