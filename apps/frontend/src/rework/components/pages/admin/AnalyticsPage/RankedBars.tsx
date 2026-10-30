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

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import type { ColorTheme } from "@shared/utils/Type";
import { formatValue, NO_VALUE } from "./analyticsFormat";
import styles from "./AnalyticsPage.module.css";

export interface RankedRow {
  key: string;
  label: string;
  value: number;
  /** The value as written at the end of the row, e.g. "640 users". */
  valueText: string;
}

interface RankedListProps {
  title: string;
  titleAction?: ReactNode;
  rows: RankedRow[];
  emptyMessage: string;
  isLoading: boolean;
  isError: boolean;
  /** Rows stay in the given order (ordered buckets) instead of being ranked. */
  keepOrder?: boolean;
}

/** A nested block ranking rows by value: name, a bar relative to the largest row, then the value. */
export function RankedList({
  title,
  titleAction,
  rows,
  emptyMessage,
  isLoading,
  isError,
  keepOrder = false,
}: RankedListProps) {
  const { t } = useTranslation();
  const sorted = keepOrder ? rows : [...rows].sort((a, b) => b.value - a.value);
  const max = Math.max(0, ...rows.map((row) => row.value));
  return (
    <section className={styles.block} aria-label={title}>
      <div className={styles.blockHeader}>
        <h3 className={styles.blockTitle}>{title}</h3>
        {titleAction}
      </div>
      {isError ? (
        <p role="alert" className={styles.note}>
          {t("common.loadingError")}
        </p>
      ) : isLoading ? (
        <p role="status" className={styles.note}>
          {t("common.loading")}
        </p>
      ) : !sorted.length ? (
        <p role="status" className={styles.note}>
          {emptyMessage}
        </p>
      ) : (
        <ul className={styles.rankList}>
          {sorted.map((row) => (
            <li key={row.key} className={styles.rankRow}>
              <span className={styles.rankLabel} title={row.label}>
                {row.label}
              </span>
              <span className={styles.thickBar}>
                <ProgressBar theme="tertiary" current={row.value} max={max} aria-label={row.label} />
              </span>
              <span className={styles.rankValue}>{row.valueText}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** A share (0 to 1) as a bar and its percent, for a table cell; empty without a value. */
export function BarCell({
  share,
  theme = "primary",
  emphasize = false,
}: {
  share: number | null;
  theme?: ColorTheme;
  /** Writes the percent in the bar's colour, bold: a value to act on. */
  emphasize?: boolean;
}) {
  const { i18n } = useTranslation();
  if (share == null) return <span className={styles.numeric}>{NO_VALUE}</span>;
  const text = formatValue(share, "percent", i18n.language);
  return (
    <span className={styles.barCell}>
      <span className={styles.thickBar}>
        <ProgressBar theme={theme} current={share} max={1} aria-label={text} />
      </span>
      <span className={styles.barCellValue} data-tone={emphasize ? theme : undefined}>
        {text}
      </span>
    </span>
  );
}

/** Two parts of a whole side by side in one bar, with "72 % / 28 %" after it. */
export function SplitCell({ first, second, label }: { first: number; second: number; label: string }) {
  const { i18n } = useTranslation();
  const total = first + second;
  const pct = (v: number) => formatValue(total ? v / total : 0, "percent", i18n.language);
  return (
    <span className={styles.barCell}>
      <span className={styles.splitBar} role="img" aria-label={`${label}: ${pct(first)} / ${pct(second)}`}>
        <span className={styles.splitFirst} style={{ width: `${total ? (first / total) * 100 : 0}%` }} />
        <span className={styles.splitSecond} />
      </span>
      <span className={styles.barCellValue}>
        {pct(first)} / {pct(second)}
      </span>
    </span>
  );
}
