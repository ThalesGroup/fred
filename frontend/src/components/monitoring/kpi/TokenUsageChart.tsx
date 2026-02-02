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

import { alpha, useTheme } from "@mui/material/styles";
import dayjs, { ManipulateType } from "dayjs";
import utc from "dayjs/plugin/utc";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MetricsResponse } from "../../../slices/agentic/agenticOpenApi";
import { precisionToUnit } from "../timeAxis";

dayjs.extend(utc);

export interface TokenUsageChartProps {
  start: Date;
  end: Date;
  precision: string; // "sec" | "min" | "hour" | "day"
  metrics: MetricsResponse;

  /** clamp chart height from parent (prevents overflow) */
  height?: number;
  /** shared numeric x-domain across charts */
  xDomain?: [number, number];
}

export function TokenUsageChart({ start, end, precision, metrics, height = 220, xDomain }: TokenUsageChartProps) {
  const theme = useTheme();

  // Choose a bar base color from your theme (prefer chart.* then primary)
  const chartPalette: any = (theme.palette as any).chart || {};
  const baseBar = chartPalette.blue || chartPalette.primary || theme.palette.primary.main;
  const barColor = alpha(baseBar, theme.palette.mode === "dark" ? 0.7 : 0.55);

  // --- helpers ---------------------------------------------------------------

  const unit: ManipulateType = precisionToUnit[precision] ?? "minute";

  const fmtX = (ts: number) => {
    const d = dayjs.utc(ts);
    if (precision === "sec") return d.format("HH:mm:ss");
    if (precision === "min") return d.format("HH:mm");
    if (precision === "hour") return d.format("MMM D HH:mm");
    return d.format("YYYY-MM-DD");
  };

  // --- map backend buckets by exact UTC millisecond --------------------------
  const bucketMap = new Map<number, number>();
  for (const b of metrics?.buckets ?? []) {
    const ms = new Date(b.timestamp).getTime(); // UTC parse
    const raw =
      (b.aggregations as any)["total_tokens_sum"] ??
      (b.aggregations as any)["total_tokens:sum"] ??
      (b.aggregations as any)["total_tokens"] ??
      0;
    const num = Array.isArray(raw) ? Number(raw[0] ?? 0) : Number(raw ?? 0);
    bucketMap.set(ms, num);
  }

  // --- build continuous series from start..end at the chosen precision -------
  const series: { ts: number; tokens: number }[] = [];
  let cur = dayjs.utc(start).startOf(unit);
  const endUtc = dayjs.utc(end).endOf(unit);

  while (cur.isBefore(endUtc) || cur.isSame(endUtc)) {
    const ts = cur.valueOf(); // ms
    const tokens = bucketMap.get(ts) ?? 0;
    series.push({ ts, tokens });
    cur = cur.add(1, unit);
  }

  // half-bucket padding so the first/last bars don't hug the Y-axes
  const stepMsFor = (p: string) => {
    if (p === "sec") return 1_000;
    if (p === "min") return 60_000;
    if (p === "hour") return 3_600_000;
    if (p === "day") return 86_400_000;
    return 60_000;
  };
  const stepMs = stepMsFor(precision);
  const paddedDomain: [number, number] | ["dataMin", "dataMax"] = xDomain
    ? [xDomain[0] - stepMs / 2, xDomain[1] + stepMs / 2]
    : ["dataMin", "dataMax"];

  // --- render ----------------------------------------------------------------
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={series} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="2 2" stroke={theme.palette.divider} />
        <XAxis
          dataKey="ts"
          type="number"
          domain={paddedDomain}
          allowDataOverflow
          padding={{ left: 6, right: 6 }}
          tickFormatter={fmtX}
          tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
        />
        <YAxis tick={{ fontSize: 11, fill: theme.palette.text.secondary }} width={44} />
        <Tooltip
          contentStyle={{
            backgroundColor: theme.palette.background.paper,
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 8,
            color: theme.palette.text.primary,
            boxShadow: theme.shadows[2] as any,
            padding: 8,
          }}
          itemStyle={{ color: theme.palette.text.secondary }}
          labelStyle={{ color: theme.palette.text.secondary }}
          cursor={{ fill: theme.palette.action.hover }}
          labelFormatter={(label) => fmtX(Number(label))}
          formatter={(val: any) => [Number(val), "tokens"]}
        />
        <Bar dataKey="tokens" fill={barColor} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
