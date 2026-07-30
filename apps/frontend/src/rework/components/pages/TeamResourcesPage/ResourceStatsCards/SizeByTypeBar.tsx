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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { BarChart as RechartsBarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import styles from "./SizeByTypeBar.module.css";

// Same pattern as BarChart.tsx's own local hook: Recharts' Tooltip is a plain
// DOM node outside the SVG, styled via inline `contentStyle`/`labelStyle` —
// it does not pick up theme CSS automatically, so its colors are read from
// computed custom properties on this section (light/dark-aware for free).
function useCssVars(ref: React.RefObject<HTMLElement | null>, ...names: string[]) {
  const [vars, setVars] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!ref.current) return;
    const style = getComputedStyle(ref.current);
    setVars(Object.fromEntries(names.map((n) => [n, style.getPropertyValue(n).trim()])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref.current]);
  return vars;
}

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
  /** Heading shown above the segment rows inside the hover tooltip. Without
   * it, Recharts falls back to the (meaningless, always-0) index of this
   * chart's single data row as the tooltip's own label. */
  tooltipTitle: string;
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
  tooltipTitle,
}: SizeByTypeBarProps) {
  const { t } = useTranslation();
  const sectionRef = useRef<HTMLElement>(null);
  const css = useCssVars(
    sectionRef,
    "--surface-container-highest",
    "--outline-retreat",
    "--on-surface",
    "--on-surface-retreat",
    "--font-family-base",
    "--radius-s",
  );
  const nonZero = segments.filter((segment) => segment.value > 0);
  const data = [Object.fromEntries(nonZero.map((segment) => [segment.key, segment.value]))];
  // "dataMax" (Recharts' own keyword) resolves to the largest INDIVIDUAL
  // series value, not the stacked total — with stackId set, the bar's real
  // right edge is the sum of every segment, which is >= that keyword's
  // result. A domain smaller than the real total pushes the last segment(s)
  // past the plot's right edge and off the visible chart entirely. A
  // literal computed total is the only way to guarantee they match.
  const total = nonZero.reduce((sum, segment) => sum + segment.value, 0);

  return (
    <section ref={sectionRef} className={styles.section}>
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
                {/* Without explicit axes, Recharts defaults BOTH to type="category" —
                    the single row's segment values are then treated as discrete
                    categories instead of a proportional numeric scale, so the stack
                    never renders its real widths. type="number"/"category" here is
                    what actually makes the bar's segments proportional to size_bytes;
                    hide removes the (meaningless, single-row) tick/axis line. */}
                <XAxis type="number" hide domain={[0, total]} />
                <YAxis type="category" hide />
                <Tooltip
                  cursor={false}
                  allowEscapeViewBox={{ x: true, y: true }}
                  wrapperStyle={{ zIndex: 1 }}
                  labelFormatter={() => tooltipTitle}
                  contentStyle={{
                    background: css["--surface-container-highest"],
                    border: `1px solid ${css["--outline-retreat"]}`,
                    borderRadius: css["--radius-s"],
                    color: css["--on-surface"],
                    fontSize: 12,
                    fontFamily: css["--font-family-base"],
                  }}
                  labelStyle={{ color: css["--on-surface-retreat"] }}
                  itemStyle={{ color: css["--on-surface"] }}
                  formatter={(value: number, key: string) => [
                    formatValue(value),
                    nonZero.find((segment) => segment.key === key)?.label ?? key,
                  ]}
                />
                {nonZero.map((segment) => (
                  <Bar
                    key={segment.key}
                    dataKey={segment.key}
                    stackId="size"
                    fill={segment.color}
                    // A tiny share (e.g. a handful of KB next to a multi-GB corpus)
                    // rounds to a 0px-wide rect — indistinguishable from the segment
                    // being altogether absent/broken. Floors every segment's own
                    // rendered width at 1px so it's always at least visible.
                    minPointSize={1}
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
