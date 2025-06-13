import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { NumericalMetric, Precision } from "../../slices/monitoringApi";
import dayjs from "dayjs";

export interface TokenUsageChartProps {
  start: Date;
  end: Date;
  precision: Precision;
  metrics: NumericalMetric[];
}

export function TokenUsageChart({ start, end, precision, metrics }: TokenUsageChartProps) {
  function getBucketKey(date: Date): string {
    const d = dayjs(date);
    switch (precision) {
      case "day":
        return d.format("YYYY-MM-DD");
      case "hour":
        return d.format("YYYY-MM-DD HH:00");
      case "min":
        return d.format("YYYY-MM-DD HH:mm");
      case "sec":
      default:
        return d.format("YYYY-MM-DD HH:mm:ss");
    }
  }

  // Label formatting for X axis, rounded for "round" numbers
  function getLabel(date: Date): string {
    const d = dayjs(date);
    switch (precision) {
      case "day":
        return d.format("DD MMMM");
      case "hour":
        return d.format("HH:00");
      case "min":
        // Only show label for "round" 10-minutes (e.g., 16:00, 16:10, 16:20)
        return d.minute() % 10 === 0 ? d.format("HH:mm") : "";
      case "sec":
      default:
        // Only show label for "round" 5-minutes (e.g., 16:00:00, 16:05:00)
        return d.second() === 0 && d.minute() % 5 === 0 ? d.format("HH:mm:ss") : "";
    }
  }

  const metricMap = new Map(metrics.map((m) => [m.bucket, m]));

  // Generate all buckets between start and end according to precision
  const data: { time: string; tokens: number }[] = [];
  let current = dayjs(start);
  const endTime = dayjs(end);

  function incrementDate(date: dayjs.Dayjs) {
    switch (precision) {
      case "day":
        return date.add(1, "day");
      case "hour":
        return date.add(1, "hour").startOf("hour");
      case "min":
        return date.add(1, "minute").startOf("minute");
      case "sec":
      default:
        return date.add(1, "second").startOf("second");
    }
  }

  while (current.isBefore(endTime) || current.isSame(endTime)) {
    // Retrieve the metric for the current time (if it exists)
    const key = getBucketKey(current.toDate());
    const metric = metricMap.get(key);

    data.push({
      time: getLabel(current.toDate()),
      tokens: metric ? (metric.values["token_usage.total_tokens"] ?? 0) : 0,
    });

    current = incrementDate(current);
  }

  // Filter ticks to only those with a label
  const ticks = data.map((d, i) => (d.time ? i : null)).filter((i) => i !== null) as number[];

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="time" ticks={ticks.map((i) => data[i].time)} />
        <YAxis />
        <Tooltip />
        <Bar dataKey="tokens" fill="#8884d8" />
      </BarChart>
    </ResponsiveContainer>
  );
}
