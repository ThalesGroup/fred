// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import dayjs, { ManipulateType } from "dayjs";
import { useTheme } from "@mui/material/styles";
import { MetricsResponse } from "../../slices/agentic/agenticOpenApi";

export interface TokenUsageChartProps {
  start: Date;
  end: Date;
  precision: string; // "sec" | "min" | "hour" | "day"
  metrics: MetricsResponse;
}

export function TokenUsageChart({ start, end, precision, metrics }: TokenUsageChartProps) {
  const theme = useTheme();

  const precisionToUnit: Record<string, ManipulateType> = {
    sec: "second",
    min: "minute",
    hour: "hour",
    day: "day",
  };

  function getBucketKey(date: Date): string {
    return dayjs(date).utc().format("YYYY-MM-DDTHH:mm:ss[Z]");
  }

  function getLabel(date: Date): string {
    const d = dayjs(date);
    switch (precision) {
      case "day":
        return d.format("DD MMM");
      case "hour":
        return d.format("HH:00");
      case "min":
        return d.minute() % 10 === 0 ? d.format("HH:mm") : "";
      case "sec":
      default:
        return d.second() === 0 && d.minute() % 5 === 0 ? d.format("HH:mm:ss") : "";
    }
  }

  // Map of timestamp -> token value
  const metricMap = new Map(
    (metrics.buckets || []).map((b) => [b.timestamp, b.aggregations["total_tokens_sum"] ?? 0])
  );

  // Debug: show available bucket keys
  console.log("[TokenChart] metricMap keys:", Array.from(metricMap.keys()));
  console.log("[TokenChart] precision:", precision);
  console.log("[TokenChart] start:", start.toISOString(), "end:", end.toISOString());

  const data: { time: string; tokens: number }[] = [];
  const unit = precisionToUnit[precision] || "minute";
  let current = dayjs.utc(start).startOf(unit);
  const endTime = dayjs.utc(end).endOf(unit);
  

  while (current.isBefore(endTime) || current.isSame(endTime)) {
    const key = getBucketKey(current.toDate());
    const val = metricMap.get(key) ?? 0;
    const numberValue = Array.isArray(val) ? val[0] ?? 0 : val;

    // Debug: log each computed key and value
    console.log("[TokenChart] key:", key, "| value:", numberValue);

    data.push({
      time: getLabel(current.toDate()),
      tokens: numberValue,
    });

    current = current.add(1, unit);
  }

  console.log("[TokenChart] total points:", data.length);

  const ticks = data
    .map((d, i) => (d.time ? i : null))
    .filter((i) => i !== null) as number[];

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="time" ticks={ticks.map((i) => data[i].time)} />
        <YAxis />
        <Tooltip />
        <Bar dataKey="tokens" fill={theme.palette.primary.main} />
      </BarChart>
    </ResponsiveContainer>
  );
}
