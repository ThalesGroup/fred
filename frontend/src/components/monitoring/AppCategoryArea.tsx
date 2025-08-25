// Copyright Thales 2025
// Apache-2.0

import { Box } from "@mui/material";
import { useTheme, alpha } from "@mui/material/styles";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { buildStackedByCategory } from "./metricChartUtils";

type Props = {
  metrics: { precision?: string; buckets?: any[] } | undefined;
  valueKey: "store_size_bytes_sum" | "docs_count_sum";
  height?: number;
  xDomain: [number, number];
  tsFmt: (ts: number) => string;
  yTickFormatter?: (n: number) => string;
  showLegend?: boolean;
};

export default function AppCategoryArea({
  metrics,
  valueKey,
  height = 220,
  xDomain,
  tsFmt,
  yTickFormatter,
  showLegend = true,
}: Props) {
  const theme = useTheme();
  const series = buildStackedByCategory(metrics, valueKey);

  // Build a soft, theme-aware series palette from your theme.palette.chart
  const chart = (theme.palette as any).chart || {};
  const bases: string[] = [
    chart.primary,
    chart.secondary,
    chart.blue,
    chart.green,
    chart.orange,
    chart.purple,
    chart.red,
    chart.yellow,
    chart.highBlue,
    chart.mediumBlue,
    chart.highGreen,
    chart.mediumGreen,
  ].filter(Boolean);
  // Fallback to core palette if chart.* is missing
  if (bases.length === 0) {
    bases.push(
      theme.palette.primary.main,
      theme.palette.secondary.main,
      theme.palette.success.main,
      theme.palette.info.main,
      theme.palette.warning.main,
      theme.palette.error.main
    );
  }
  const fillAlpha = theme.palette.mode === "dark" ? 0.28 : 0.22;
  const fills = bases.map((hex) => alpha(hex, fillAlpha));

  return (
    <Box sx={{ width: "100%", height }}>
      <ResponsiveContainer>
        <AreaChart data={series.data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 2" stroke={theme.palette.divider} />
          <XAxis
            dataKey="ts"
            type="number"
            domain={xDomain}
            tickFormatter={tsFmt}
            tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
          />
          <YAxis
            tickFormatter={yTickFormatter ?? ((n) => n)}
            tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
            width={yTickFormatter ? 56 : 44}
          />
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
            cursor={{ stroke: theme.palette.divider, strokeWidth: 1 }}
            formatter={(val: any, key: any) => [
              yTickFormatter ? (yTickFormatter as any)(Number(val)) : Number(val),
              key,
            ]}
            labelFormatter={(label) => tsFmt(Number(label))}
          />
          {showLegend && (
            <Legend
              verticalAlign="top"
              height={20}
              wrapperStyle={{ fontSize: 11, color: theme.palette.text.secondary as any }}
              iconType="circle"
            />
          )}

          {series.keys.map((k, i) => {
            const fill = fills[i % fills.length];
            const stroke = alpha(fill, theme.palette.mode === "dark" ? 0.9 : 0.8);
            return (
              <Area
                key={k}
                type="monotone"
                dataKey={k}
                stackId="1"
                stroke={stroke}
                fill={fill}
                dot={false}
                activeDot={{
                  r: 3,
                  fill: stroke,
                  stroke: theme.palette.background.paper,
                  strokeWidth: 2,
                }}
              />
            );
          })}
        </AreaChart>
      </ResponsiveContainer>
    </Box>
  );
}

// (optional) re-export if you still need it elsewhere:
// export { formatBytes } from "./metricChartUtils";
