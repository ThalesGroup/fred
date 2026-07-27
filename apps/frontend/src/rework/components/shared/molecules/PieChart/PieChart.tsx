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
import { PieChart as RechartsPieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { LabelValuePoint } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PieChart.module.scss";

function getCssVars(...names: string[]): Record<string, string> {
  const style = getComputedStyle(document.documentElement);
  return Object.fromEntries(names.map((n) => [n, style.getPropertyValue(n).trim()]));
}

interface PieChartProps {
  title: string;
  rows: LabelValuePoint[];
  emptyMessage?: string;
  isLoading: boolean;
  isError: boolean;
  /** Slice colors, one per row in order. Defaults to the 2-tone
   *  primary/tertiary pair (unchanged default behavior); pass the shared
   *  `SERIES_COLORS` (from `MultiSeriesLineChart`) for 3+ categorical
   *  slices instead of picking new hex values. */
  colors?: string[];
  /** Shrinks padding/title/chart to fit a ~120px-tall card (e.g. a dashboard tile
   *  row) instead of the roomier default section. The legend moves beside the
   *  pie (using width, not height) and shrinks to fit the same band. */
  compact?: boolean;
}

export default function PieChart({
  title,
  rows,
  emptyMessage,
  isLoading,
  isError,
  colors,
  compact = false,
}: PieChartProps) {
  const { t } = useTranslation();
  const css = getCssVars(
    "--on-surface-retreat",
    "--outline-retreat",
    "--surface-container-highest",
    "--on-surface",
    "--primary",
    "--tertiary",
    "--font-family-base",
    "--radius-s",
  );

  const COLORS = colors ?? [css["--primary"], css["--tertiary"]];

  return (
    <section className={styles.section} data-compact={compact || undefined}>
      <div className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
      </div>

      {isLoading && !rows.length && <div className={styles.state}>{t("common.loading")}</div>}
      {isError && <div className={styles.stateError}>{t("common.loadingError")}</div>}
      {!isLoading && !isError && !rows.length && (
        <div className={styles.state}>{emptyMessage ?? t("common.noData")}</div>
      )}

      {!!rows.length && (
        <div className={styles.chartArea}>
          <ResponsiveContainer width="100%" height={compact ? 76 : 220}>
            <RechartsPieChart margin={compact ? { top: 0, right: 0, left: 0, bottom: 0 } : undefined}>
              <Pie
                data={rows}
                dataKey="value"
                nameKey="label"
                cx={compact ? "30%" : "50%"}
                cy="50%"
                outerRadius={compact ? 30 : 80}
                strokeWidth={0}
              >
                {rows.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: css["--surface-container-highest"],
                  border: `1px solid ${css["--outline-retreat"]}`,
                  borderRadius: css["--radius-s"],
                  color: css["--on-surface"],
                  fontSize: 12,
                  fontFamily: css["--font-family-base"],
                }}
                itemStyle={{ color: css["--on-surface"] }}
                labelStyle={{ color: css["--on-surface-retreat"] }}
                formatter={(value: number, name: string) => [value.toLocaleString(), name]}
              />
              <Legend
                layout={compact ? "vertical" : "horizontal"}
                verticalAlign={compact ? "middle" : "bottom"}
                align={compact ? "right" : "center"}
                iconSize={compact ? 6 : 14}
                wrapperStyle={{
                  fontSize: compact ? 9 : 12,
                  lineHeight: compact ? "1.4" : undefined,
                  fontFamily: css["--font-family-base"],
                  color: css["--on-surface-retreat"],
                }}
              />
            </RechartsPieChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
