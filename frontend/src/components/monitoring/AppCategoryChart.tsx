// src/components/metrics/AppCategoryCharts.tsx
// Copyright Thales 2025
// Apache-2.0

import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from "recharts";
import dayjs from "dayjs";
import { Box } from "@mui/material";

type MetricsBucket = {
  timestamp: string;
  group: Record<string, any>;
  aggregations: Record<string, number | number[]>;
};

type MetricsResponse = {
  precision: "sec" | "min" | "hour" | "day";
  buckets: MetricsBucket[];
};

type CommonProps = {
  metrics: MetricsResponse;
  valueKey: "store_size_bytes_sum" | "docs_count_sum";
  yTickFormatter?: (n: number) => string;
};

/** Build stacked series by `category` over time from MetricsResponse. */
function buildStackedSeries(metrics: MetricsResponse, valueKey: string) {
  const byTs = new Map<number, Record<string, number>>();
  const seriesKeys = new Set<string>();

  for (const b of metrics.buckets || []) {
    const ts = new Date(b.timestamp).getTime();
    const cat = (b.group?.category ?? "other") as string;
    const val = Number(b.aggregations?.[valueKey] ?? 0);
    seriesKeys.add(cat);

    const row = byTs.get(ts) ?? { ts };
    row[cat] = (row[cat] ?? 0) + val;
    byTs.set(ts, row);
  }

  const data = Array.from(byTs.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([ts, row]) => ({ ts, ...row }));

  return { data, keys: Array.from(seriesKeys).sort() };
}

const palette = [
  "#7cb5ec","#90ed7d","#f7a35c","#8085e9","#f15c80",
  "#e4d354","#2b908f","#f45b5b","#91e8e1","#8d4653",
];

function tsFormatter(precision: MetricsResponse["precision"]) {
  return (ts: number) => {
    const d = dayjs(ts);
    if (precision === "sec") return d.format("HH:mm:ss");
    if (precision === "min") return d.format("HH:mm");
    if (precision === "hour") return d.format("MMM D HH:mm");
    return d.format("YYYY-MM-DD");
  };
}

function defaultBytes(n: number) {
  if (!Number.isFinite(n)) return "-";
  const units = ["B","KB","MB","GB","TB","PB"];
  let v = n, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(2)} ${units[i]}`;
}

export function AppStoreSizeChart({ metrics, valueKey, yTickFormatter }: CommonProps) {
  const { data, keys } = buildStackedSeries(metrics, valueKey);
  const fmtX = tsFormatter(metrics.precision);

  return (
    <Box sx={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="ts"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={fmtX}
          />
          <YAxis tickFormatter={yTickFormatter ?? defaultBytes} />
          <Tooltip
            formatter={(val: any, key: any) => [val as number, key]}
            labelFormatter={(label) => fmtX(Number(label))}
          />
          <Legend />
          {keys.map((k, i) => (
            <Area
              key={k}
              type="monotone"
              dataKey={k}
              stackId="1"
              stroke={palette[i % palette.length]}
              fill={palette[i % palette.length]}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </Box>
  );
}

export function AppDocsCountChart({ metrics, valueKey }: CommonProps) {
  const { data, keys } = buildStackedSeries(metrics, valueKey);
  const fmtX = tsFormatter(metrics.precision);

  return (
    <Box sx={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="ts"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={fmtX}
          />
          <YAxis />
          <Tooltip
            formatter={(val: any, key: any) => [val as number, key]}
            labelFormatter={(label) => fmtX(Number(label))}
          />
          <Legend />
          {keys.map((k, i) => (
            <Area
              key={k}
              type="monotone"
              dataKey={k}
              stackId="1"
              stroke={palette[i % palette.length]}
              fill={palette[i % palette.length]}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </Box>
  );
}
