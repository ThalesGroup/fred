// Copyright Thales 2025
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

import {
  Box,
  Button,
  Collapse,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
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
import type { ChartPart, ChartType } from "../../slices/agentic/agenticOpenApi.ts";
import {
  axisTickProps,
  categoricalChartPalette,
  gridStroke,
  legendStyle,
  tooltipStyle,
} from "../monitoring/kpi/metricChartUtils";

type ChartRendererProps = { part: ChartPart };

const CHART_HEIGHT = 320;
// Above this raw character count, X-axis labels (e.g. long GBU/domain names) are
// slanted so they stay readable instead of overlapping or being clipped.
const X_LABEL_SLANT_THRESHOLD = 10;
// Slanted ticks are truncated to keep the axis compact; the full value still
// shows in the tooltip on hover.
const X_TICK_MAX = 22;

/** Coerce a cell value to a finite number, or null when not numeric. */
function toNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const n = Number(value.trim());
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/**
 * ChartRenderer (presentational)
 *
 * Renders the self-contained rows carried by a ChartPart. The agent picks the
 * most fitting visualization per result (bar for comparisons, line/area for
 * trends, pie for compositions) and we honor that `chart_type` directly — there
 * is no client-side type switcher. The raw rows stay one click away via a
 * collapsible table at the bottom. Reuses the KPI chart styling helpers so
 * charts match the rest of the app.
 */
export default function ChartRenderer({ part }: ChartRendererProps) {
  const theme = useTheme();
  const { t } = useTranslation();

  const rows = part.rows ?? [];
  const xKey = part.x_key;
  const yKeys = (part.y_keys ?? []).length > 0 ? (part.y_keys as string[]) : [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  // The agent chose the chart type; the table is offered separately on demand.
  const chartType: ChartType = part.chart_type ?? "bar";
  const [showTable, setShowTable] = useState(false);

  // Coerce y values to numbers so recharts plots them reliably (DuckDB may
  // surface numerics as strings through the JSON transport).
  const chartData = useMemo(
    () =>
      rows.map((row) => {
        const out: Record<string, unknown> = { [xKey]: row[xKey] };
        for (const key of yKeys) out[key] = toNumber(row[key]);
        return out;
      }),
    [rows, xKey, yKeys],
  );

  const pieData = useMemo(() => {
    const valueKey = yKeys[0];
    if (!valueKey) return [];
    return rows
      .map((row) => ({ name: String(row[xKey] ?? ""), value: toNumber(row[valueKey]) ?? 0 }))
      .filter((d) => Number.isFinite(d.value));
  }, [rows, xKey, yKeys]);

  // Bold, fully legible series for inline chat charts (the monitoring default is
  // intentionally soft). Areas keep a strong outline but a translucent fill so
  // overlapping bands stay readable.
  const seriesCount = Math.max(yKeys.length, pieData.length);
  const palette = categoricalChartPalette(theme, seriesCount, 0.92);
  const areaFillPalette = categoricalChartPalette(theme, seriesCount, theme.palette.mode === "dark" ? 0.32 : 0.22);
  // Hover highlight that *strengthens* the hovered column instead of washing it
  // out the way Recharts' default light-grey cursor does on a dark background.
  // Mirrors the design-system hover state layer `--state-on-surface-hover`
  // (on-surface at 8%); text.primary === --on-surface, so it flips per mode.
  const hoverCursorFill = alpha(theme.palette.text.primary, 0.08);
  const showLegend = yKeys.length > 1;

  const isEmpty = rows.length === 0;

  // Slant the X axis only when at least one category label is long, so trend
  // charts (short month keys) keep flat labels.
  const slantXLabels = chartData.some((d) => String(d[xKey] ?? "").length > X_LABEL_SLANT_THRESHOLD);

  const renderSlantedTick = ({ x, y, payload }: { x: number; y: number; payload: { value: unknown } }) => {
    const raw = String(payload?.value ?? "");
    const label = raw.length > X_TICK_MAX ? `${raw.slice(0, X_TICK_MAX - 1)}…` : raw;
    return (
      <text
        x={x}
        y={y}
        dy={4}
        textAnchor="end"
        transform={`rotate(-35, ${x}, ${y})`}
        fontSize={11}
        fill={theme.palette.text.secondary}
      >
        {label}
      </text>
    );
  };

  const xAxisProps = {
    dataKey: xKey,
    height: slantXLabels ? 92 : 30,
    interval: slantXLabels ? (0 as const) : undefined,
    tickMargin: slantXLabels ? 8 : 4,
    tick: slantXLabels ? renderSlantedTick : axisTickProps(theme),
  };

  const renderTable = () => (
    <TableContainer sx={{ maxHeight: CHART_HEIGHT }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            {columns.map((col) => (
              <TableCell key={col} sx={{ fontWeight: 600 }}>
                {col}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, idx) => (
            <TableRow key={idx} hover>
              {columns.map((col) => (
                <TableCell key={col}>{row[col] == null ? "—" : String(row[col])}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const renderChart = () => {
    if (isEmpty) {
      return <Box sx={{ p: 2, fontSize: 13, color: theme.palette.text.secondary }}>{t("chat.chart.noData")}</Box>;
    }

    if (chartType === "table") {
      return renderTable();
    }

    if (chartType === "pie") {
      return (
        <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
          <PieChart>
            <Tooltip contentStyle={tooltipStyle(theme)} />
            {showLegend && <Legend wrapperStyle={legendStyle(theme)} />}
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              outerRadius={120}
              label
              stroke={theme.palette.background.paper}
              strokeWidth={2}
            >
              {pieData.map((entry, idx) => (
                <Cell key={entry.name + idx} fill={palette[idx % palette.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      );
    }

    if (chartType === "line") {
      return (
        <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
          <LineChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke={gridStroke(theme)} />
            <XAxis {...xAxisProps} />
            <YAxis tick={axisTickProps(theme)} width={56} />
            <Tooltip
              contentStyle={tooltipStyle(theme)}
              cursor={{ stroke: theme.palette.text.secondary, strokeWidth: 1, strokeDasharray: "3 3" }}
            />
            {showLegend && <Legend wrapperStyle={legendStyle(theme)} />}
            {yKeys.map((key, idx) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={palette[idx % palette.length]}
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 5, strokeWidth: 0 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
    }

    if (chartType === "area") {
      return (
        <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
          <AreaChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke={gridStroke(theme)} />
            <XAxis {...xAxisProps} />
            <YAxis tick={axisTickProps(theme)} width={56} />
            <Tooltip
              contentStyle={tooltipStyle(theme)}
              cursor={{ stroke: theme.palette.text.secondary, strokeWidth: 1, strokeDasharray: "3 3" }}
            />
            {showLegend && <Legend wrapperStyle={legendStyle(theme)} />}
            {yKeys.map((key, idx) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={palette[idx % palette.length]}
                strokeWidth={2.5}
                fill={areaFillPalette[idx % areaFillPalette.length]}
                fillOpacity={1}
                activeDot={{ r: 5, strokeWidth: 0 }}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      );
    }

    // default: bar
    return (
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 2" stroke={gridStroke(theme)} />
          <XAxis {...xAxisProps} />
          <YAxis tick={axisTickProps(theme)} width={56} />
          <Tooltip contentStyle={tooltipStyle(theme)} cursor={{ fill: hoverCursorFill }} />
          {showLegend && <Legend wrapperStyle={legendStyle(theme)} />}
          {yKeys.map((key, idx) => (
            <Bar
              key={key}
              dataKey={key}
              fill={palette[idx % palette.length]}
              radius={[3, 3, 0, 0]}
              activeBar={{ fillOpacity: 1, stroke: theme.palette.text.primary, strokeWidth: 1 }}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  };

  return (
    <Paper elevation={3} sx={{ my: 2, p: 1.5, borderRadius: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }} noWrap>
        {part.title || t("chat.chart.title")}
      </Typography>

      {renderChart()}

      {/* Raw rows are always one click away, even when a chart is shown. */}
      {!isEmpty && chartType !== "table" && (
        <Box sx={{ mt: 0.5 }}>
          <Button
            size="small"
            variant="text"
            onClick={() => setShowTable((v) => !v)}
            sx={{ textTransform: "none", color: theme.palette.text.secondary }}
          >
            {showTable ? t("chat.chart.hideData") : t("chat.chart.showData")}
          </Button>
          <Collapse in={showTable} unmountOnExit>
            <Box sx={{ mt: 1 }}>{renderTable()}</Box>
          </Collapse>
        </Box>
      )}

      {part.sql && (
        <Typography
          variant="caption"
          component="pre"
          sx={{
            mt: 1,
            display: "block",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontFamily: "monospace",
            color: theme.palette.text.secondary,
          }}
        >
          {part.sql}
        </Typography>
      )}
    </Paper>
  );
}
