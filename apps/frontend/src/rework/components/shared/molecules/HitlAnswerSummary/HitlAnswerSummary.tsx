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
import type { HitlAnswerSummary as Summary } from "@rework/utils/hitlAnswerSummary";
import styles from "./HitlAnswerSummary.module.css";

interface HitlAnswerSummaryProps {
  summary: Summary;
  inTrace?: boolean;
}

export function HitlAnswerSummary({ summary, inTrace = false }: HitlAnswerSummaryProps) {
  const { t } = useTranslation();
  return (
    <div
      className={`${styles.card} ${inTrace ? styles.inTrace : ""}`}
      role="group"
      aria-label={t("rework.hitlPrompt.answerSummary")}
    >
      <p className={styles.question}>{summary.question}</p>
      <p className={styles.answer}>{summary.skipped ? t("rework.hitlPrompt.skipped") : summary.answer}</p>
      {summary.comment && !summary.skipped && <p className={styles.comment}>{summary.comment}</p>}
    </div>
  );
}
