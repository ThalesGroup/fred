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
  ComposedChart,
  Funnel,
  FunnelChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
} from "recharts";
import { SERIES_COLORS } from "../../components/shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import type { ChartPart } from "../../../slices/runtime/runtimeOpenApi";
import type { UiPartRendererProps } from "./types";
import { chartColumns, downloadChartExcel, downloadChartPng } from "./chartPartExport";
import styles from "./chartPartRenderer.module.css";

const chartTypes = new Set([
  "bar",
  "bar_horizontal",
  "bar_stacked",
  "line",
  "area",
  "area_stacked",
  "pie",
  "donut",
  "scatter",
  "radar",
  "radial_bar",
  "funnel",
  "treemap",
  "composed",
  "table",
]);
const singleNonnegative = new Set(["pie", "donut", "radial_bar", "funnel", "treemap"]);
const numberPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/;

function scalar(value: unknown): boolean {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  );
}

function validGroupRows(rows: ChartPart["rows"], xKey: string, groupKey: string): boolean {
  const pairs = new Set<string>();
  const groups = new Set<string>();
  for (const row of rows) {
    const group = row[groupKey];
    if (
      (typeof group !== "string" && typeof group !== "number") ||
      (typeof group === "number" && !Number.isFinite(group))
    )
      return false;
    const groupId = JSON.stringify(group);
    const pair = JSON.stringify([row[xKey], group]);
    if (pairs.has(pair)) return false;
    pairs.add(pair);
    groups.add(groupId);
  }
  return groups.size <= 8;
}

function barGroupKey(part: ChartPart): string | null {
  if (!["bar", "bar_horizontal", "bar_stacked"].includes(part.chart_type) || part.y_keys?.length !== 1 || !part.x_key)
    return null;
  if (part.group_key) return part.group_key;
  const extraKeys = Object.keys(part.rows[0]).filter((key) => key !== part.x_key && key !== part.y_keys[0]);
  if (extraKeys.length !== 1 || !part.rows.every((row) => Object.keys(row).length === 3)) return null;
  const key = extraKeys[0];
  const categories = new Set(part.rows.map((row) => JSON.stringify(row[part.x_key!])));
  const groups = new Set(part.rows.map((row) => JSON.stringify(row[key])));
  return categories.size < part.rows.length && groups.size > 1 && validGroupRows(part.rows, part.x_key, key)
    ? key
    : null;
}

function groupedBarData(part: ChartPart, groupKey: string) {
  const xKey = part.x_key!;
  const yKey = part.y_keys![0];
  const groups = [...new Map(part.rows.map((row) => [JSON.stringify(row[groupKey]), row[groupKey]])).values()];
  const series = groups.map((group, index) => ({ key: `__chart_group_${index}`, name: String(group) }));
  const seriesByGroup = new Map(groups.map((group, index) => [JSON.stringify(group), series[index].key]));
  const categories = new Map<string, Record<string, string | number | boolean | null>>();
  for (const row of part.rows) {
    const categoryId = JSON.stringify(row[xKey]);
    let category = categories.get(categoryId);
    if (!category) {
      category = { __chart_category: row[xKey] };
      categories.set(categoryId, category);
    }
    category[seriesByGroup.get(JSON.stringify(row[groupKey]))!] = row[yKey] === null ? null : Number(row[yKey]);
  }
  return { rows: [...categories.values()], series };
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
  if (part.chart_type === "table") return part.group_key == null;
  const xKey = part.x_key;
  const yKeys = part.y_keys;
  if (
    typeof xKey !== "string" ||
    !Array.isArray(yKeys) ||
    yKeys.length === 0 ||
    yKeys.length > 8 ||
    ((singleNonnegative.has(String(part.chart_type)) || part.chart_type === "scatter") && yKeys.length !== 1) ||
    (part.chart_type === "composed" && yKeys.length < 2)
  )
    return false;
  if (
    part.group_key != null &&
    (typeof part.group_key !== "string" ||
      !part.group_key ||
      !["bar", "bar_horizontal", "bar_stacked"].includes(String(part.chart_type)) ||
      yKeys.length !== 1 ||
      part.group_key === xKey ||
      part.group_key === yKeys[0] ||
      !validGroupRows(part.rows, xKey, part.group_key))
  )
    return false;
  return part.rows.every(
    (row) =>
      xKey in row &&
      (part.chart_type !== "scatter" ||
        ((typeof row[xKey] === "number" || (typeof row[xKey] === "string" && numberPattern.test(row[xKey]))) &&
          Number.isFinite(Number(row[xKey])))) &&
      yKeys.every((key) => {
        if (typeof key !== "string" || !(key in row)) return false;
        const value = row[key];
        if (value === null) return true;
        if (typeof value === "string" && !numberPattern.test(value)) return false;
        if (typeof value !== "string" && typeof value !== "number") return false;
        const number = Number(value);
        return Number.isFinite(number) && (!singleNonnegative.has(String(part.chart_type)) || number >= 0);
      }),
  );
}

function rawValue(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function TreemapTile({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  index = 0,
  labelKey,
  ...row
}: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  labelKey: string;
  [key: string]: unknown;
}) {
  const label = String(row[labelKey] ?? "");
  return (
    <svg x={x} y={y} width={width} height={height} overflow="hidden" aria-label={label}>
      <rect
        x={0}
        y={0}
        width={width}
        height={height}
        fill={SERIES_COLORS[index % SERIES_COLORS.length]}
        stroke="var(--surface-floating)"
      />
      {width > 50 && height > 24 && (
        <text x={8} y={18} fill="#fff" stroke="#111" strokeWidth={2} paintOrder="stroke" fontSize={12}>
          {label}
        </text>
      )}
    </svg>
  );
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
    ...(part.chart_type === "scatter" && part.x_key ? { [part.x_key]: Number(row[part.x_key]) } : {}),
  }));
  const xKey = part.x_key ?? "";
  const yKeys = part.y_keys ?? [];
  const groupKey = barGroupKey(part);
  const grouped = groupKey ? groupedBarData(part, groupKey) : null;
  const plotXKey = grouped ? "__chart_category" : xKey;
  const categoricalTooltip = (
    <Tooltip
      contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }}
      itemStyle={{ color: "var(--on-surface)" }}
    />
  );
  // Recharts discovers chart primitives among direct children.
  const axes = [
    <CartesianGrid key="grid" stroke="var(--outline-muted)" strokeDasharray="3 3" vertical={false} />,
    <XAxis
      key="x-axis"
      dataKey={plotXKey}
      tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }}
      interval="preserveStartEnd"
    />,
    <YAxis key="y-axis" tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }} />,
    <Tooltip key="tooltip" contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }} />,
    <Legend key="legend" />,
  ];
  const horizontalAxes = [
    <CartesianGrid key="grid" stroke="var(--outline-muted)" strokeDasharray="3 3" horizontal={false} />,
    <XAxis key="x-axis" type="number" tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }} />,
    <YAxis
      key="y-axis"
      type="category"
      dataKey={plotXKey}
      width={100}
      tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }}
    />,
    <Tooltip key="tooltip" contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }} />,
    <Legend key="legend" />,
  ];
  let plot = null;
  if (["bar", "bar_horizontal", "bar_stacked"].includes(part.chart_type)) {
    const horizontal = part.chart_type === "bar_horizontal";
    plot = (
      <BarChart data={grouped?.rows ?? data} layout={horizontal ? "vertical" : "horizontal"}>
        {horizontal ? horizontalAxes : axes}
        {(grouped?.series ?? yKeys.map((key) => ({ key, name: key }))).map(({ key, name }, index) => (
          <Bar
            key={key}
            dataKey={key}
            name={name}
            stackId={part.chart_type === "bar_stacked" ? "total" : undefined}
            fill={SERIES_COLORS[index % SERIES_COLORS.length]}
          />
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
  } else if (part.chart_type === "area" || part.chart_type === "area_stacked") {
    plot = (
      <AreaChart data={data}>
        {axes}
        {yKeys.map((key, index) => (
          <Area
            key={key}
            dataKey={key}
            stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
            fill={SERIES_COLORS[index % SERIES_COLORS.length]}
            stackId={part.chart_type === "area_stacked" ? "total" : undefined}
          />
        ))}
      </AreaChart>
    );
  } else if (part.chart_type === "pie" || part.chart_type === "donut") {
    plot = (
      <PieChart>
        <Pie
          data={data}
          dataKey={yKeys[0]}
          nameKey={xKey}
          innerRadius={part.chart_type === "donut" ? 60 : 0}
          outerRadius={110}
          label
        >
          {data.map((_, index) => (
            <Cell key={index} fill={SERIES_COLORS[index % SERIES_COLORS.length]} />
          ))}
        </Pie>
        {categoricalTooltip}
        <Legend />
      </PieChart>
    );
  } else if (part.chart_type === "scatter") {
    plot = (
      <ScatterChart>
        <CartesianGrid stroke="var(--outline-muted)" strokeDasharray="3 3" />
        <XAxis type="number" dataKey={xKey} name={xKey} tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }} />
        <YAxis
          type="number"
          dataKey={yKeys[0]}
          name={yKeys[0]}
          tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }}
        />
        <Tooltip contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }} />
        <Scatter name={yKeys[0]} data={data} fill={SERIES_COLORS[0]} />
      </ScatterChart>
    );
  } else if (part.chart_type === "radar") {
    plot = (
      <RadarChart data={data}>
        <PolarGrid stroke="var(--outline-muted)" />
        <PolarAngleAxis dataKey={xKey} tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }} />
        <PolarRadiusAxis tick={{ fill: "var(--on-surface-retreat)", fontSize: 11 }} />
        <Tooltip contentStyle={{ background: "var(--surface-floating)", color: "var(--on-surface)" }} />
        <Legend />
        {yKeys.map((key, index) => (
          <Radar
            key={key}
            name={key}
            dataKey={key}
            stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
            fill={SERIES_COLORS[index % SERIES_COLORS.length]}
            fillOpacity={0.25}
          />
        ))}
      </RadarChart>
    );
  } else if (part.chart_type === "radial_bar") {
    plot = (
      <RadialBarChart data={data} innerRadius="20%" outerRadius="90%">
        <RadialBar
          dataKey={yKeys[0]}
          background
          isAnimationActive={false}
          label={{ dataKey: xKey, position: "insideStart", fill: "var(--on-surface)" }}
        >
          {data.map((_, index) => (
            <Cell key={index} fill={SERIES_COLORS[index % SERIES_COLORS.length]} />
          ))}
        </RadialBar>
        {categoricalTooltip}
      </RadialBarChart>
    );
  } else if (part.chart_type === "funnel") {
    plot = (
      <FunnelChart>
        <Funnel data={data} dataKey={yKeys[0]} nameKey={xKey} isAnimationActive={false}>
          {data.map((_, index) => (
            <Cell key={index} fill={SERIES_COLORS[index % SERIES_COLORS.length]} />
          ))}
          <LabelList dataKey={xKey} position="right" fill="var(--on-surface)" stroke="none" />
        </Funnel>
        {categoricalTooltip}
      </FunnelChart>
    );
  } else if (part.chart_type === "treemap") {
    plot = (
      <Treemap data={data} dataKey={yKeys[0]} nameKey={xKey} content={<TreemapTile labelKey={xKey} />}>
        {categoricalTooltip}
      </Treemap>
    );
  } else if (part.chart_type === "composed") {
    plot = (
      <ComposedChart data={data}>
        {axes}
        <Bar dataKey={yKeys[0]} fill={SERIES_COLORS[0]} />
        {yKeys.slice(1).map((key, index) => (
          <Line key={key} dataKey={key} stroke={SERIES_COLORS[(index + 1) % SERIES_COLORS.length]} />
        ))}
      </ComposedChart>
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
