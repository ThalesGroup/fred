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
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SERIES_COLORS } from "../../components/shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import type { ChartPart } from "../../../slices/runtime/runtimeOpenApi";
import type { UiPartRendererProps } from "./types";
import styles from "./chartPartRenderer.module.css";

const chartTypes = new Set(["bar", "line", "area", "pie", "table"]);
const numberPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/;

function scalar(value: unknown): boolean {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  );
}

function validChart(part: UiPartRendererProps["part"]): part is UiPartRendererProps["part"] & ChartPart {
  if (
    !chartTypes.has(String(part.chart_type)) ||
    typeof part.title !== "string" ||
    !Array.isArray(part.rows) ||
    part.rows.length === 0 ||
    part.rows.length > 50 ||
    (part.y_keys !== undefined &&
      (!Array.isArray(part.y_keys) || !part.y_keys.every((key) => typeof key === "string"))) ||
    !part.rows.every((row) => row && typeof row === "object" && !Array.isArray(row) && Object.values(row).every(scalar))
  ) {
    return false;
  }
  if (part.chart_type === "table") return true;
  const xKey = part.x_key;
  const yKeys = part.y_keys;
  if (typeof xKey !== "string" || !Array.isArray(yKeys) || yKeys.length === 0 || yKeys.length > 8) return false;
  return part.rows.every(
    (row) =>
      xKey in row &&
      yKeys.every((key) => {
        if (typeof key !== "string" || !(key in row)) return false;
        const value = row[key];
        if (value === null) return true;
        if (typeof value === "string" && !numberPattern.test(value)) return false;
        if (typeof value !== "string" && typeof value !== "number") return false;
        const number = Number(value);
        return Number.isFinite(number) && (part.chart_type !== "pie" || number >= 0);
      }),
  );
}

function rawValue(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

export function ChartPartRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  if (!validChart(part)) return <p>{t("chat.chart.unavailable")}</p>;

  const columns = [...new Set(part.rows.flatMap((row) => Object.keys(row)))];
  const data = part.rows.map((row) => ({
    ...row,
    ...Object.fromEntries((part.y_keys ?? []).map((key) => [key, row[key] === null ? null : Number(row[key])])),
  }));
  const xKey = part.x_key ?? "";
  const yKeys = part.y_keys ?? [];
  // Recharts discovers chart primitives among direct children.
  const axes = [
    <CartesianGrid key="grid" stroke="var(--outline-muted)" strokeDasharray="3 3" vertical={false} />,
    <XAxis
      key="x-axis"
      dataKey={xKey}
      tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }}
      interval="preserveStartEnd"
    />,
    <YAxis key="y-axis" tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }} />,
    <Tooltip key="tooltip" contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }} />,
    <Legend key="legend" />,
  ];
  let plot = null;
  if (part.chart_type === "bar") {
    plot = (
      <BarChart data={data}>
        {axes}
        {yKeys.map((key, index) => (
          <Bar key={key} dataKey={key} fill={SERIES_COLORS[index % SERIES_COLORS.length]} />
        ))}
      </BarChart>
    );
  } else if (part.chart_type === "line") {
    plot = (
      <LineChart data={data}>
        {axes}
        {yKeys.map((key, index) => (
          <Line key={key} dataKey={key} stroke={SERIES_COLORS[index % SERIES_COLORS.length]} connectNulls={false} />
        ))}
      </LineChart>
    );
  } else if (part.chart_type === "area") {
    plot = (
      <AreaChart data={data}>
        {axes}
        {yKeys.map((key, index) => (
          <Area
            key={key}
            dataKey={key}
            stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
            fill={SERIES_COLORS[index % SERIES_COLORS.length]}
          />
        ))}
      </AreaChart>
    );
  } else if (part.chart_type === "pie") {
    plot = (
      <PieChart>
        <Pie data={data} dataKey={yKeys[0]} nameKey={xKey} outerRadius={110} label>
          {data.map((_, index) => (
            <Cell key={index} fill={SERIES_COLORS[index % SERIES_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }} />
        <Legend />
      </PieChart>
    );
  }

  return (
    <section className={styles.panel} aria-label={part.title}>
      <h3 className={styles.title}>{part.title}</h3>
      {plot && (
        <div className={styles.plot}>
          <ResponsiveContainer width="100%" height="100%">
            {plot}
          </ResponsiveContainer>
        </div>
      )}
      <details open={part.chart_type === "table"}>
        <summary>{t("chat.chart.data")}</summary>
        <div className={styles.tableScroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th scope="col" key={column}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {part.rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>{rawValue(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
