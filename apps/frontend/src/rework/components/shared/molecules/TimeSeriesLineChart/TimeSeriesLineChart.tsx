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
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { TimeSeriesPoint } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TimeSeriesLineChart.module.scss";

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

interface TimeSeriesLineChartProps {
  title: string;
  rows: TimeSeriesPoint[];
  interval?: string;
  valueLabel?: string;
  isFetching: boolean;
  isLoading: boolean;
  isError: boolean;
}

export default function TimeSeriesLineChart({
  title,
  rows,
  interval,
  valueLabel,
  isFetching,
  isLoading,
  isError,
}: TimeSeriesLineChartProps) {
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

  return (
    <section ref={sectionRef} className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          {title}
          {interval && <span className={styles.intervalBadge}>{interval}</span>}
        </h2>
      </div>

      {(isLoading || isFetching) && !rows.length && <div className={styles.state}>{t("common.loading")}</div>}
      {isError && <div className={styles.stateError}>{t("common.loadingError")}</div>}

      {!!rows.length && (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={css["--outline-retreat"]} />
            <XAxis
              dataKey="date"
              tick={{ fill: css["--on-surface-retreat"], fontSize: 11, fontFamily: css["--font-family-base"] }}
              tickLine={false}
              axisLine={{ stroke: css["--outline-retreat"] }}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fill: css["--on-surface-retreat"], fontSize: 11, fontFamily: css["--font-family-base"] }}
              tickLine={false}
              axisLine={false}
              width={32}
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
            <Line
              type="monotone"
              dataKey="value"
              stroke={css["--primary"]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: css["--primary"] }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </section>
  );
}
