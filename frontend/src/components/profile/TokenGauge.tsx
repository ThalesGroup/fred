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

interface TokenGaugeProps {
  tokens: number;
  maxTokens: number;
}

export const TokenGauge = ({ tokens, maxTokens }: TokenGaugeProps) => {
  const usage = Math.min((tokens / maxTokens) * 100, 100);

  const option = {
    series: [
      {
        type: "gauge",
        startAngle: 180,
        endAngle: 0,
        radius: "100%",
        center: ["50%", "75%"],
        min: 0,
        max: 100,
        splitNumber: 2,
        axisLine: {
          lineStyle: {
            width: 12,
            color: [
              [0.5, "#91cc75"],
              [0.85, "#fac858"],
              [1, "#ee6666"]
            ]
          }
        },
        pointer: {
          show: false
        },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: {
          formatter: `{value}%`,
          fontSize: 12,
          offsetCenter: [0, "-20%"]
        },
        data: [{ value: usage }]
      }
    ]
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: 100, width: "100%" }}
      opts={{ renderer: "svg" }}
    />
  );
};
