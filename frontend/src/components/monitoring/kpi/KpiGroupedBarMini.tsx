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

import { useMemo } from "react";
import { Box } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip, Legend, BarChart, Bar } from "recharts";
import type { KpiQueryResultRow } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { axisTickProps, gridStroke, tooltipStyle, legendStyle, primarySeriesColor } from "./metricChartUtils";

type MetricKey = keyof NonNullable<KpiQueryResultRow["metrics"]>;

/**
 * KpiGroupedBarMini (presentational)
 *
 * Input: KPI rows grouped by a single group field with a single metric alias.
 * Output: compact bar chart for top groups (sorted desc).
 */
export function KpiGroupedBarMini({
  rows,
  groupKey,
  metricKey,
  metricLabel,
  height = 150,
  showLegend = false,
  maxItems = 8,
}: {
  rows: KpiQueryResultRow[];
  groupKey: string;
  metricKey: MetricKey;
  metricLabel: string;
  height?: number;
  showLegend?: boolean;
  maxItems?: number;
}) {
  const theme = useTheme();

  const data = useMemo(() => {
    const normalized = (rows ?? []).map((r) => ({
      k: (r.group as any)?.[groupKey] ?? "unknown",
      v: Number((r.metrics as any)?.[metricKey] ?? 0),
    }));
    return normalized
      .filter((d) => Number.isFinite(d.v))
      .sort((a, b) => b.v - a.v)
      .slice(0, maxItems);
  }, [rows, groupKey, metricKey, maxItems]);

  const isEmpty = data.length === 0;

  return (
    <Box sx={{ width: "100%", height }}>
      <ResponsiveContainer>
        {isEmpty ? (
          <Box sx={{ p: 1, fontSize: 12, color: theme.palette.text.secondary }}>No data in the selected range.</Box>
        ) : (
          <BarChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke={gridStroke(theme)} />
            <XAxis dataKey="k" tick={axisTickProps(theme)} />
            <YAxis tick={axisTickProps(theme)} width={56} />
            <Tooltip contentStyle={tooltipStyle(theme)} formatter={(val: any) => Number(val).toFixed(1)} />
            {showLegend && <Legend wrapperStyle={legendStyle(theme)} />}
            <Bar dataKey="v" name={metricLabel} fill={primarySeriesColor(theme)} radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </Box>
  );
}
