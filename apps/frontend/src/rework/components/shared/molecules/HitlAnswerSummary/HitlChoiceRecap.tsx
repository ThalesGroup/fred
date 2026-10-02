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
import type { HitlAnswerSummary } from "@rework/utils/hitlAnswerSummary";
import styles from "./HitlChoiceRecap.module.css";

export function HitlChoiceRecap({ summary }: { summary: HitlAnswerSummary }) {
  const { t } = useTranslation();
  const freeTextChoice =
    !summary.skipped && summary.choiceId === null && summary.choices.length > 0 && !!summary.answer;
  return (
    <div className={styles.recap}>
      <p className={styles.question}>{summary.question}</p>
      {summary.choices.length > 0 && (
        <div className={styles.choices} role="list">
          {summary.choices.map((choice) => {
            const selected = !summary.skipped && summary.choiceId === choice.id;
            return (
              <div key={choice.id} className={styles.choice} data-selected={selected || undefined} role="listitem">
                <span className={styles.label}>{choice.label}</span>
                {selected && <span className={styles.selected}>{t("rework.hitlPrompt.selected")}</span>}
                {choice.description && <span className={styles.description}>{choice.description}</span>}
              </div>
            );
          })}
          {freeTextChoice && (
            <div className={styles.choice} data-selected="true" role="listitem">
              <span className={styles.label}>{t("chatbot.hitlOtherAnswerWithText", { answer: summary.answer })}</span>
              <span className={styles.selected}>{t("rework.hitlPrompt.selected")}</span>
            </div>
          )}
        </div>
      )}
      {summary.skipped ? (
        <p className={styles.response}>{t("rework.hitlPrompt.skipped")}</p>
      ) : !summary.choiceId || !summary.choices.some((choice) => choice.id === summary.choiceId) ? (
        summary.answer && !freeTextChoice && <p className={styles.response}>{summary.answer}</p>
      ) : null}
      {summary.comment && !summary.skipped && <p className={styles.comment}>{summary.comment}</p>}
    </div>
  );
}
