import ReactECharts from "echarts-for-react";
import DashboardCard from "./DashboardCard";
import { NumericalMetric } from "../../slices/monitoringApi"; // Adjust if import path is different

type Props = {
  metrics: NumericalMetric[];
};

export default function MetricChart({ metrics }: Props) {
  const times = metrics.map(m => new Date(m.bucket).toLocaleTimeString());
  const latencies = metrics.map(m => m.values["latency"] ?? 0);
  const totalTokens = metrics.map(m => m.values["token_usage.total_tokens"] ?? 0);

  const option = {
    tooltip: {
      trigger: "axis",
    },
    legend: {
      data: ["Latency (s)", "Total Tokens"],
    },
    xAxis: {
      type: "category",
      data: times,
    },
    yAxis: [
      {
        type: "value",
        name: "Latency (s)",
      },
      {
        type: "value",
        name: "Tokens",
      },
    ],
    series: [
      {
        name: "Latency (s)",
        type: "line",
        data: latencies,
        yAxisIndex: 0,
      },
      {
        name: "Total Tokens",
        type: "bar",
        data: totalTokens,
        yAxisIndex: 1,
      },
    ],
  };

  return (
    <DashboardCard title="LLM Call Latency & Token Usage">
      <ReactECharts option={option} style={{ height: 400 }} />
    </DashboardCard>
  );
}
