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
import {
  ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip, Legend, BarChart, Bar,
} from "recharts";
import type { KpiQueryResultRow } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { axisTickProps, gridStroke, tooltipStyle, legendStyle, primarySeriesColor } from "./metricChartUtils";

/**
 * KpiStatusMini (presentational)
 *
 * Why (Fred): keep tiles dumb — the page owns fetching and passes rows down.
 * Input: rows from the KPI query (grouped by dims.status with alias "exchanges").
 * Output: compact bar chart, no time axis.
 */
export function KpiStatusMini({
  rows,
  height = 150,
  showLegend = false,
}: {
  rows: KpiQueryResultRow[];
  height?: number;
  showLegend?: boolean;
}) {
  const theme = useTheme();

  // Normalize rows -> [{ k, v }]
  const data = useMemo(
    () =>
      (rows ?? []).map((r) => ({
        k: (r.group as any)?.["dims.status"] ?? "unknown",
        v: Number(r.metrics?.exchanges ?? 0),
      })),
    [rows]
  );

  const isEmpty = data.length === 0;

  return (
    <Box sx={{ width: "100%", height }}>
      <ResponsiveContainer>
        {isEmpty ? (
          <Box sx={{ p: 1, fontSize: 12, color: theme.palette.text.secondary }}>
            No data in the selected range.
          </Box>
        ) : (
          <BarChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke={gridStroke(theme)} />
            <XAxis dataKey="k" tick={axisTickProps(theme)} />
            <YAxis tick={axisTickProps(theme)} width={44} allowDecimals={false} />
            <Tooltip contentStyle={tooltipStyle(theme)} />
            {showLegend && <Legend wrapperStyle={legendStyle(theme)} />}
            <Bar dataKey="v" name="exchanges" fill={primarySeriesColor(theme)} radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </Box>
  );
}
