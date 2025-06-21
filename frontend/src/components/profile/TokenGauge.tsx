// components/profile/TokenGauge.tsx
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
