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
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
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

const CHART_TYPES: ChartType[] = ["bar", "line", "area", "pie", "table"];
const CHART_HEIGHT = 320;

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
 * Renders the self-contained rows carried by a ChartPart emitted by the SQL
 * agent. The agent proposes a chart type + column mapping; the user can switch
 * the chart type client-side (no re-query) and fall back to a raw table.
 * Reuses the KPI chart styling helpers so charts match the rest of the app.
 */
export default function ChartRenderer({ part }: ChartRendererProps) {
  const theme = useTheme();
  const { t } = useTranslation();

  const rows = part.rows ?? [];
  const xKey = part.x_key;
  const yKeys = (part.y_keys ?? []).length > 0 ? (part.y_keys as string[]) : [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  const [chartType, setChartType] = useState<ChartType>(part.chart_type ?? "bar");

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

  const renderChart = () => {
    if (isEmpty) {
      return <Box sx={{ p: 2, fontSize: 13, color: theme.palette.text.secondary }}>{t("chat.chart.noData")}</Box>;
    }

    if (chartType === "table") {
      return (
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
            <XAxis dataKey={xKey} tick={axisTickProps(theme)} />
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
            <XAxis dataKey={xKey} tick={axisTickProps(theme)} />
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
          <XAxis dataKey={xKey} tick={axisTickProps(theme)} />
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
      <Box
        sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, mb: 1, flexWrap: "wrap" }}
      >
        <Typography variant="subtitle2" noWrap>
          {part.title || t("chat.chart.title")}
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={chartType}
          onChange={(_, next) => next && setChartType(next as ChartType)}
          aria-label={t("chat.chart.type")}
        >
          {CHART_TYPES.map((type) => (
            <ToggleButton key={type} value={type} sx={{ textTransform: "none", px: 1 }}>
              {t(`chat.chart.${type}`)}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      {renderChart()}

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
