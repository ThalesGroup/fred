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
import { BarChart as RechartsBarChart, Bar, Tooltip, ResponsiveContainer } from "recharts";
import styles from "./SizeByTypeBar.module.css";

export interface SizeByTypeSegment {
  key: string;
  label: string;
  value: number;
  color: string;
}

interface SizeByTypeBarProps {
  title: string;
  segments: SizeByTypeSegment[];
  isLoading: boolean;
  isError: boolean;
  emptyMessage?: string;
  /** Formats one segment's raw value for the tooltip and legend (e.g. bytes -> "1.2 MB"). */
  formatValue: (value: number) => string;
}

/**
 * A single full-width horizontal bar, its length split into colored segments
 * proportional to each file type's share of total size — a "how is this
 * corpus's storage spent" glance, not a per-category comparison (that's the
 * files-by-type histogram's job). Deliberately not built on the generic
 * `BarChart` molecule: that one draws one bar per category on separate rows,
 * this draws one row with N stacked series — a different chart shape, not a
 * variant of the same one.
 */
export default function SizeByTypeBar({
  title,
  segments,
  isLoading,
  isError,
  emptyMessage,
  formatValue,
}: SizeByTypeBarProps) {
  const { t } = useTranslation();
  const nonZero = segments.filter((segment) => segment.value > 0);
  const data = [Object.fromEntries(nonZero.map((segment) => [segment.key, segment.value]))];

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
      </div>

      {isLoading && !nonZero.length && <div className={styles.state}>{t("common.loading")}</div>}
      {isError && <div className={styles.stateError}>{t("common.loadingError")}</div>}
      {!isLoading && !isError && !nonZero.length && (
        <div className={styles.state}>{emptyMessage ?? t("common.noData")}</div>
      )}

      {!!nonZero.length && (
        <>
          <div className={styles.barWrapper}>
            <ResponsiveContainer width="100%" height={22}>
              <RechartsBarChart
                data={data}
                layout="vertical"
                barSize={22}
                margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
              >
                <Tooltip
                  cursor={false}
                  formatter={(value: number, key: string) => [
                    formatValue(value),
                    nonZero.find((segment) => segment.key === key)?.label ?? key,
                  ]}
                />
                {nonZero.map((segment, i) => (
                  <Bar
                    key={segment.key}
                    dataKey={segment.key}
                    stackId="size"
                    fill={segment.color}
                    radius={
                      // Rounded outer corners only, like one continuous rounded bar — not
                      // every segment individually rounded, which would look like beads.
                      [
                        i === 0 ? 4 : 0,
                        i === nonZero.length - 1 ? 4 : 0,
                        i === nonZero.length - 1 ? 4 : 0,
                        i === 0 ? 4 : 0,
                      ]
                    }
                  />
                ))}
              </RechartsBarChart>
            </ResponsiveContainer>
          </div>
          <ul className={styles.legend}>
            {nonZero.map((segment) => (
              <li key={segment.key} className={styles.legendItem}>
                <span className={styles.legendDot} style={{ "--dot-color": segment.color } as React.CSSProperties} />
                {segment.label}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
