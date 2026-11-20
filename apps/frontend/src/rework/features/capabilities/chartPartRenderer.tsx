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

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { OptionModel } from "@models/Option.model";
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
import { chartColumns, downloadChartExcel, downloadChartPng } from "./chartPartExport";
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
  if (
    typeof xKey !== "string" ||
    !Array.isArray(yKeys) ||
    yKeys.length === 0 ||
    yKeys.length > 8 ||
    (part.chart_type === "pie" && yKeys.length !== 1)
  )
    return false;
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
  const { showError } = useToast();
  const plotRef = useRef<HTMLDivElement>(null);
  if (!validChart(part)) return <p>{t("chat.chart.unavailable")}</p>;

  const columns = chartColumns(part.rows);
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
        <Tooltip
          contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }}
          itemStyle={{ color: "var(--on-surface)" }}
        />
        <Legend />
      </PieChart>
    );
  }

  const options: OptionModel<"excel" | "png">[] = [
    {
      value: "excel",
      key: "excel",
      label: t("chat.chart.downloadExcel"),
      icon: { category: "outlined", type: "table_chart" },
    },
    ...(plot
      ? [
          {
            value: "png" as const,
            key: "png",
            label: t("chat.chart.downloadPng"),
            icon: { category: "outlined" as const, type: "image" as const },
          },
        ]
      : []),
  ];

  const onExport = async (format: "excel" | "png") => {
    try {
      if (format === "excel") {
        await downloadChartExcel(part.rows, part.title);
      } else {
        if (!plotRef.current) throw new Error("Chart graphic is unavailable");
        await downloadChartPng(plotRef.current, part.title);
      }
    } catch (error) {
      showError({
        summary: t("chat.chart.exportFailed", { format: format === "excel" ? "Excel" : "PNG" }),
        detail: String(error),
      });
    }
  };

  return (
    <section className={styles.panel} aria-label={part.title}>
      <div className={styles.header}>
        <h3 className={styles.title}>{part.title}</h3>
        <IconButtonMenu
          iconButton={{
            color: "on-surface",
            variant: "icon",
            size: "small",
            icon: { category: "outlined", type: "download" },
            "aria-label": t("chat.chart.download"),
          }}
          options={options}
          onSelect={(format) => void onExport(format)}
        />
      </div>
      {plot && (
        <div className={styles.plot} ref={plotRef}>
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
