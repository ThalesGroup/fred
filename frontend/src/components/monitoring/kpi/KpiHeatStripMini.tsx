// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Box, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import dayjs, { ManipulateType } from "dayjs";
import utc from "dayjs/plugin/utc";
import type { ReactNode } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { KpiQueryResultRow } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { precisionToUnit } from "../timeAxis";

dayjs.extend(utc);

type KpiHeatStripMiniProps = {
  label: ReactNode;
  rows: KpiQueryResultRow[];
  metricKey: string;
  start: Date;
  end: Date;
  precision: string;
  height?: number;
  xDomain?: [number, number];
  labelMinWidth?: number;
  frame?: boolean;
  dense?: boolean;
};

const toNumber = (value: unknown) => (typeof value === "number" && !Number.isNaN(value) ? value : null);

export const KpiHeatStripMini = ({
  label,
  rows,
  metricKey,
  start,
  end,
  precision,
  height = 22,
  xDomain,
  labelMinWidth = 80,
  frame = true,
  dense = false,
}: KpiHeatStripMiniProps) => {
  const theme = useTheme();
  const unit: ManipulateType = precisionToUnit[precision] ?? "minute";
  const hasLabel = !(label === "" || label === null || label === undefined);
  const labelGap = hasLabel ? 1.25 : 0;

  const bucketMap = new Map<number, { value: number | null; hasData: boolean }>();
  for (const row of rows ?? []) {
    const ts = Date.parse((row.group as any)?.time ?? "");
    if (!Number.isFinite(ts)) continue;
    const value = toNumber((row.metrics as any)?.[metricKey]);
    const hasData = (row.doc_count ?? 0) > 0;
    bucketMap.set(ts, { value, hasData });
  }

  const series: { ts: number; value: number; hasData: boolean }[] = [];
  let cur = dayjs.utc(start).startOf(unit);
  const endUtc = dayjs.utc(end).endOf(unit);
  while (cur.isBefore(endUtc) || cur.isSame(endUtc)) {
    const ts = cur.valueOf();
    const entry = bucketMap.get(ts);
    series.push({
      ts,
      value: entry?.value ?? 0,
      hasData: entry?.hasData ?? false,
    });
    cur = cur.add(1, unit);
  }
  const colorFor = (value: number | null, count: number) => {
    if (!count || value == null) return alpha(theme.palette.text.secondary, 0.25);
    if (value >= 90) return theme.palette.error.main;
    if (value >= 80) return theme.palette.warning.main;
    if (value >= 60) return theme.palette.info.main;
    return theme.palette.success.main;
  };

  const fmtX = (ts: number) => {
    const d = dayjs.utc(ts);
    if (precision === "sec") return d.format("HH:mm:ss");
    if (precision === "min") return d.format("HH:mm");
    if (precision === "hour") return d.format("MMM D HH:mm");
    return d.format("YYYY-MM-DD");
  };

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

  return (
    <Box
      sx={{
        p: dense ? 0 : 1,
        borderRadius: frame ? 2 : 0,
        border: frame ? `1px solid ${theme.palette.divider}` : "none",
        bgcolor: frame ? theme.palette.background.default : "transparent",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: labelGap }}>
        {hasLabel &&
          (typeof label === "string" ? (
            <Typography variant="caption" sx={{ minWidth: labelMinWidth, color: theme.palette.text.secondary }}>
              {label}
            </Typography>
          ) : (
            <Box
              sx={{
                minWidth: labelMinWidth,
                color: theme.palette.text.secondary,
                display: "flex",
                alignItems: "center",
              }}
            >
              {label}
            </Box>
          ))}
        <Box
          sx={{
            flex: 1,
            height,
          }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={series} margin={{ top: 0, right: 0, left: 0, bottom: 0 }} barCategoryGap={0} barGap={0}>
              <XAxis dataKey="ts" type="number" domain={paddedDomain} hide />
              <YAxis hide domain={[0, 100]} />
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
                formatter={(val: any) => [`${Number(val).toFixed(1)}%`, label]}
              />
              <Bar dataKey="value" isAnimationActive={false} radius={[2, 2, 2, 2]}>
                {series.map((entry, idx) => (
                  <Cell
                    key={`${label}-cell-${idx}`}
                    fill={colorFor(entry.hasData ? entry.value : null, entry.hasData ? 1 : 0)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Box>
      </Box>
    </Box>
  );
};
