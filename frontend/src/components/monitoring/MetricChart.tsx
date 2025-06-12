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
