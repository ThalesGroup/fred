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
}

export default function PieChart({ title, rows, emptyMessage, isLoading, isError }: PieChartProps) {
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

  const COLORS = [css["--primary"], css["--tertiary"]];

  return (
    <section className={styles.section}>
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
          <ResponsiveContainer width="100%" height={220}>
            <RechartsPieChart>
              <Pie data={rows} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={80} strokeWidth={0}>
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
                wrapperStyle={{
                  fontSize: 12,
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
