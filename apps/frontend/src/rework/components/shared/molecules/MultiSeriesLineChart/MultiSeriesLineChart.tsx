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

import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Bar,
  ComposedChart,
  LabelList,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import styles from "./MultiSeriesLineChart.module.scss";

// Distinct palette — works on both light and dark surfaces. Exported so other
// multi-category charts (e.g. the Resources stat cards) can reuse the same
// vetted set instead of picking new hex values.
export const SERIES_COLORS = [
  "#4e8cff",
  "#f97316",
  "#22c55e",
  "#a855f7",
  "#eab308",
  "#06b6d4",
  "#ec4899",
  "#84cc16",
  "#f43f5e",
  "#64748b",
];

// Past this many buckets the value labels would collide, so the axis comes back.
const MAX_LABELLED_POINTS = 16;

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

/** One time bucket: a value per series label. Built in the page from the analytics bucket points. */
interface MultiSeriesPoint {
  date: string;
  values: Record<string, number>;
}

interface MultiSeriesLineChartProps {
  title: string;
  rows: MultiSeriesPoint[];
  series: string[];
  /** Series drawn as bars under the lines, e.g. active users under visitors. */
  barSeries?: string[];
  interval?: string;
  valueLabel?: string;
  isFetching: boolean;
  isLoading: boolean;
  isError: boolean;
  /** Drawn on the parent's surface, without a card of its own (inside a dashboard section). */
  flat?: boolean;
  /** Colour tokens per series (e.g. "--primary-container"), in place of the default palette. */
  seriesColors?: string[];
  /** Opacity per series (0–1): two tones of one colour stay readable in light and dark. */
  seriesOpacities?: number[];
  /** Values written on bars and points instead of a value axis and grid; legend in the header. */
  labelled?: boolean;
  /** Bar series stacked, with their total written above each stack. */
  stacked?: boolean;
  /** Formats the written values and the tooltip, e.g. compact token counts. */
  formatValue?: (value: number) => string;
  /** Rendered right after the title, e.g. an info icon. */
  titleAction?: ReactNode;
}

type LabelProps = {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  value?: unknown;
  index?: number;
};

export default function MultiSeriesLineChart({
  title,
  rows,
  series,
  barSeries = [],
  interval,
  valueLabel,
  isFetching,
  isLoading,
  isError,
  flat = false,
  seriesColors,
  seriesOpacities,
  labelled = false,
  stacked = false,
  formatValue,
  titleAction,
}: MultiSeriesLineChartProps) {
  const { t, i18n } = useTranslation();
  const sectionRef = useRef<HTMLElement>(null);
  const css = useCssVars(
    sectionRef,
    "--on-surface-retreat",
    "--outline-muted",
    "--outline-variant",
    "--surface-floating",
    "--surface-container",
    "--on-surface",
    "--on-primary",
    "--font-family-base",
    "--radius-s",
    ...(seriesColors ?? []),
  );
  const colorOf = (idx: number) =>
    seriesColors?.[idx] ? css[seriesColors[idx]] : SERIES_COLORS[idx % SERIES_COLORS.length];
  const format = formatValue ?? ((v: number) => v.toLocaleString(i18n.language));
  const valueLabels = labelled && rows.length <= MAX_LABELLED_POINTS;
  const bars = series.filter((name) => barSeries.includes(name));
  const lastIndex = rows.length - 1;
  const font = css["--font-family-base"];

  // Recharts needs flat objects: { date, [agentId]: value, … }
  const chartData = rows.map((row) => ({
    date: row.date,
    ...row.values,
  }));

  // A stack's total above its top segment; a single bar's value inside its top.
  const renderBarLabel = (props: LabelProps) => {
    const x = Number(props.x) + Number(props.width) / 2;
    const y = Number(props.y);
    if (stacked) {
      const point = chartData[props.index ?? 0] as Record<string, unknown>;
      const total = bars.reduce((sum, name) => sum + Number(point?.[name] ?? 0), 0);
      return (
        <text x={x} y={y - 7} textAnchor="middle" fontFamily={font} fontSize={11} fill={css["--on-surface-retreat"]}>
          {format(total)}
        </text>
      );
    }
    return (
      <text x={x} y={y + 16} textAnchor="middle" fontFamily={font} fontSize={11} fill={css["--on-primary"]}>
        {format(Number(props.value))}
      </text>
    );
  };
  // The current (last) point is the one to read: filled dot and emphasized value.
  const renderPointLabel = (props: LabelProps) => {
    const last = props.index === lastIndex;
    return (
      <text
        x={Number(props.x)}
        y={Number(props.y) - 12}
        textAnchor="middle"
        fontFamily={font}
        fontSize={11}
        fontWeight={last ? 600 : 400}
        fill={css[last ? "--on-surface" : "--on-surface-retreat"]}
      >
        {format(Number(props.value))}
      </text>
    );
  };
  const renderDot = (color: string) =>
    function Dot(props: { cx?: number; cy?: number; index?: number }) {
      const last = props.index === lastIndex;
      return (
        <circle
          key={props.index}
          cx={props.cx}
          cy={props.cy}
          r={last ? 5 : 3.5}
          fill={last ? color : css["--surface-container"]}
          stroke={color}
          strokeWidth={2}
        />
      );
    };

  return (
    <section ref={sectionRef} className={styles.section} data-flat={flat || undefined}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          {title}
          {titleAction}
          {interval && <span className={styles.intervalBadge}>{interval}</span>}
        </h2>
        {labelled && (
          <ul className={styles.legend}>
            {series.map((name, idx) => (
              <li key={name} className={styles.legendItem}>
                <span
                  className={barSeries.includes(name) ? styles.swatchBar : styles.swatchLine}
                  style={{ background: colorOf(idx), opacity: seriesOpacities?.[idx] }}
                  aria-hidden
                />
                {name}
              </li>
            ))}
          </ul>
        )}
      </div>

      {(isLoading || isFetching) && !rows.length && <div className={styles.state}>{t("common.loading")}</div>}
      {isError && <div className={styles.stateError}>{t("common.loadingError")}</div>}

      {!!rows.length && (
        <ResponsiveContainer width="100%" height={labelled ? 260 : 280}>
          <ComposedChart
            data={chartData}
            margin={
              valueLabels ? { top: 24, right: 16, left: 16, bottom: 0 } : { top: 8, right: 16, left: 0, bottom: 0 }
            }
          >
            {!valueLabels && <CartesianGrid strokeDasharray="3 3" stroke={css["--outline-muted"]} />}
            <XAxis
              dataKey="date"
              tick={{
                fill: css["--on-surface-retreat"],
                fontSize: 11,
                fontFamily: font,
              }}
              tickLine={false}
              axisLine={{ stroke: css[labelled ? "--outline-variant" : "--outline-muted"] }}
            />
            <YAxis
              allowDecimals={false}
              tick={{
                fill: css["--on-surface-retreat"],
                fontSize: 11,
                fontFamily: font,
              }}
              tickFormatter={formatValue}
              tickLine={false}
              axisLine={false}
              width={formatValue ? 48 : 32}
              hide={valueLabels}
            />
            <Tooltip
              cursor={{ stroke: css["--outline-muted"] }}
              contentStyle={{
                background: css["--surface-floating"],
                border: `1px solid ${css["--outline-muted"]}`,
                borderRadius: css["--radius-s"],
                color: css["--on-surface"],
                fontSize: 12,
                fontFamily: font,
              }}
              labelStyle={{ color: css["--on-surface-retreat"] }}
              itemStyle={{ color: css["--on-surface"] }}
              formatter={(v: number, name: string) =>
                valueLabel ? [format(v), `${name} — ${valueLabel}`] : [format(v), name]
              }
            />
            {!labelled && (
              <Legend
                wrapperStyle={{
                  fontSize: 10,
                  fontFamily: font,
                  color: css["--on-surface-retreat"],
                  // A cap, not a height: charts with a couple of series render
                  // one row either way. Sized for the top-agents ranking, whose
                  // ten labels each carry a team name and no longer fit in 44px.
                  maxHeight: 88,
                  overflowY: "auto",
                  paddingTop: 4,
                }}
              />
            )}
            {/* Bars first so the lines are drawn on top of them. */}
            {series.map(
              (name, idx) =>
                barSeries.includes(name) && (
                  <Bar
                    key={name}
                    dataKey={name}
                    fill={colorOf(idx)}
                    fillOpacity={seriesOpacities?.[idx]}
                    stackId={stacked ? "stack" : undefined}
                    radius={stacked && name !== bars[bars.length - 1] ? 0 : [4, 4, 0, 0]}
                    maxBarSize={labelled ? 48 : undefined}
                    isAnimationActive={false}
                  >
                    {valueLabels && (!stacked || name === bars[bars.length - 1]) && (
                      <LabelList dataKey={name} content={renderBarLabel} />
                    )}
                  </Bar>
                ),
            )}
            {series.map(
              (name, idx) =>
                !barSeries.includes(name) && (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={colorOf(idx)}
                    strokeWidth={2}
                    dot={valueLabels ? renderDot(colorOf(idx)) : false}
                    activeDot={{ r: 4 }}
                    isAnimationActive={false}
                  >
                    {valueLabels && <LabelList dataKey={name} content={renderPointLabel} />}
                  </Line>
                ),
            )}
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </section>
  );
}
