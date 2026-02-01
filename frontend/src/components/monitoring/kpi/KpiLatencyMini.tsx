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

import { Box } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useMemo } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { KpiQueryResultRow } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { TimePrecision, buildPaddedDomain, formatTick, iterateBuckets } from "../timeAxis";
import { axisTickProps, gridStroke, legendStyle, tooltipStyle } from "./metricChartUtils";

export function KpiLatencyMini({
  start,
  end,
  precision,
  xDomain,
  rows,
  height = 150,
  showLegend = false,
}: {
  start: Date;
  end: Date;
  precision: TimePrecision;
  xDomain?: [number, number];
  rows: KpiQueryResultRow[]; // 👈 new prop
  height?: number;
  showLegend?: boolean;
}) {
  const theme = useTheme();

  // normalize rows to continuous series
  const series = useMemo(() => {
    const byTs = new Map<number, { p50: number; p95: number }>();
    for (const r of rows) {
      const t = (r.group as any)?.time as string | undefined;
      if (!t) continue;
      byTs.set(new Date(t).getTime(), { p50: Number(r.metrics?.p50 ?? 0), p95: Number(r.metrics?.p95 ?? 0) });
    }
    return iterateBuckets(start, end, precision).map((ts) => {
      const v = byTs.get(ts);
      return { ts, p50: v ? v.p50 : null, p95: v ? v.p95 : null };
    });
  }, [rows, start, end, precision]);

  const isEmpty = series.every((p) => p.p50 == null && p.p95 == null);
  const domain = buildPaddedDomain(precision, xDomain, start, end);

  return (
    <Box sx={{ width: "100%", height }}>
      <ResponsiveContainer>
        {isEmpty ? (
          <Box sx={{ p: 1, fontSize: 12, color: theme.palette.text.secondary }}>No data in the selected range.</Box>
        ) : (
          <LineChart data={series} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke={gridStroke(theme)} />
            <XAxis
              dataKey="ts"
              type="number"
              domain={domain as any}
              allowDataOverflow
              padding={{ left: 6, right: 6 }}
              tickFormatter={(v) => formatTick(Number(v), precision)}
              tick={axisTickProps(theme)}
            />
            <YAxis tick={axisTickProps(theme)} width={44} />
            <Tooltip
              contentStyle={tooltipStyle(theme)}
              itemStyle={{ color: theme.palette.text.secondary }}
              labelStyle={{ color: theme.palette.text.secondary }}
              cursor={{ stroke: theme.palette.action.hover }}
              labelFormatter={(label) => formatTick(Number(label), precision)}
              formatter={(val: any, name) => [val == null ? "—" : Number(val).toFixed(1), name]}
            />
            {showLegend && <Legend wrapperStyle={legendStyle(theme)} />}
            <Line type="monotone" name="p50 (ms)" dataKey="p50" dot={false} connectNulls={false} />
            <Line type="monotone" name="p95 (ms)" dataKey="p95" dot={false} connectNulls={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </Box>
  );
}
