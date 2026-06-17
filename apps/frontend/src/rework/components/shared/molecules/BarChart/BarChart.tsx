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
import { BarChart as RechartsBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { LabelValuePoint } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./BarChart.module.scss";

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

interface BarChartProps {
  title: string;
  rows: LabelValuePoint[];
  valueLabel?: string;
  emptyMessage?: string;
  isLoading: boolean;
  isError: boolean;
  /** Controls row ordering. "desc" (default) sorts by value descending; "none" preserves the input order. */
  sortOrder?: "desc" | "none";
  /** Height of each bar in pixels (horizontal layout). Default 32. */
  barHeight?: number;
  /**
   * "horizontal" (default) — bars grow left-to-right, labels on the Y axis.
   * "vertical" — bars grow upward, labels on the X axis at the bottom.
   */
  orientation?: "horizontal" | "vertical";
}

export default function BarChart({
  title,
  rows,
  valueLabel,
  emptyMessage,
  isLoading,
  isError,
  sortOrder = "desc",
  barHeight = 32,
  orientation = "horizontal",
}: BarChartProps) {
  const { t } = useTranslation();
  const sectionRef = useRef<HTMLElement>(null);
  const css = useCssVars(
    sectionRef,
    "--on-surface-retreat",
    "--outline-retreat",
    "--surface-container-highest",
    "--on-surface",
    "--primary",
    "--font-family-base",
    "--radius-s",
  );

  const displayRows = sortOrder === "desc" ? [...rows].sort((a, b) => b.value - a.value) : rows;

  const isVertical = orientation === "vertical";

  // Horizontal: height grows with number of bars. Vertical: fixed height, width is unrestricted.
  const chartHeight = isVertical ? 220 : Math.max(180, displayRows.length * barHeight + 40);

  return (
    <section ref={sectionRef} className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
      </div>

      {isLoading && !rows.length && <div className={styles.state}>{t("common.loading")}</div>}
      {isError && <div className={styles.stateError}>{t("common.loadingError")}</div>}
      {!isLoading && !isError && !rows.length && (
        <div className={styles.state}>{emptyMessage ?? t("common.noData")}</div>
      )}

      {!!rows.length && (
        <div className={styles.chartWrapper}>
          <ResponsiveContainer width="100%" height={chartHeight}>
            {isVertical ? (
              <RechartsBarChart
                data={displayRows}
                layout="horizontal"
                margin={{ top: 8, right: 8, left: 8, bottom: 40 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={css["--outline-retreat"]} vertical={false} />
                <XAxis
                  type="category"
                  dataKey="label"
                  tick={{ fill: css["--on-surface-retreat"], fontSize: 11, fontFamily: css["--font-family-base"] }}
                  tickLine={false}
                  axisLine={{ stroke: css["--outline-retreat"] }}
                  angle={-35}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis
                  type="number"
                  allowDecimals={false}
                  tick={{ fill: css["--on-surface-retreat"], fontSize: 11, fontFamily: css["--font-family-base"] }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: css["--surface-container-highest"],
                    border: `1px solid ${css["--outline-retreat"]}`,
                    borderRadius: css["--radius-s"],
                    color: css["--on-surface"],
                    fontSize: 12,
                    fontFamily: css["--font-family-base"],
                  }}
                  labelStyle={{ color: css["--on-surface-retreat"] }}
                  formatter={(v: number) => (valueLabel ? [v, valueLabel] : [v])}
                />
                <Bar dataKey="value" fill={css["--primary"]} radius={[4, 4, 0, 0]} />
              </RechartsBarChart>
            ) : (
              <RechartsBarChart data={displayRows} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={css["--outline-retreat"]} horizontal={false} />
                <XAxis
                  type="number"
                  allowDecimals={false}
                  tick={{ fill: css["--on-surface-retreat"], fontSize: 11, fontFamily: css["--font-family-base"] }}
                  tickLine={false}
                  axisLine={{ stroke: css["--outline-retreat"] }}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={120}
                  tick={{ fill: css["--on-surface-retreat"], fontSize: 11, fontFamily: css["--font-family-base"] }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: css["--surface-container-highest"],
                    border: `1px solid ${css["--outline-retreat"]}`,
                    borderRadius: css["--radius-s"],
                    color: css["--on-surface"],
                    fontSize: 12,
                    fontFamily: css["--font-family-base"],
                  }}
                  labelStyle={{ color: css["--on-surface-retreat"] }}
                  formatter={(v: number) => (valueLabel ? [v, valueLabel] : [v])}
                />
                <Bar dataKey="value" fill={css["--primary"]} radius={[0, 4, 4, 0]} />
              </RechartsBarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
