import { describe, expect, it } from "vitest";

import { buildMindMapChartOption } from "./MindMapBlock";
import type { MindMapPayload } from "./mindmapParser";

const theme = {
  tooltipBackground: "#111",
  tooltipBorder: "#222",
  tooltipText: "#fff",
  lineColor: "#333",
  nodeColor: "#444",
  nodeBorder: "#555",
  labelColor: "#666",
  labelBackground: "#777",
  emphasisNodeColor: "#888",
  emphasisNodeBorder: "#999",
  emphasisLabelColor: "#aaa",
  emphasisLabelBackground: "#bbb",
  nodeSize: 12,
  labelFontSize: 14,
  labelRadius: 8,
  labelPaddingBlock: 4,
  labelPaddingInline: 8,
  nodeBorderWidth: 1,
  emphasisBorderWidth: 2,
};

function payload(
  presentation: MindMapPayload["presentation"],
): MindMapPayload {
  return {
    title: "Transcript",
    root: {
      id: "root",
      name: "Overview",
      children: [
        {
          id: "child-1",
          name: "Frontend MVP",
          children: [
            {
              id: "child-1a",
              name: "Markdown pipeline",
              children: [],
            },
          ],
        },
      ],
    },
    presentation,
  };
}

describe("buildMindMapChartOption", () => {
  it("uses payload presentation.initialDepth instead of a hardcoded level", () => {
    const option = buildMindMapChartOption(
      payload({ initialDepth: 2, layout: "orthogonal", focusMode: true }),
      theme,
    );

    const series = option.series[0];
    expect(series.initialTreeDepth).toBe(2);
  });

  it("maps orthogonal layout to ECharts orthogonal + LR orientation", () => {
    const option = buildMindMapChartOption(
      payload({ initialDepth: 2, layout: "orthogonal", focusMode: true }),
      theme,
    );

    const series = option.series[0];
    expect(series.layout).toBe("orthogonal");
    expect(series.orient).toBe("LR");
  });

  it("maps radial layout to ECharts radial layout without RL orientation", () => {
    const option = buildMindMapChartOption(
      payload({ initialDepth: 2, layout: "radial", focusMode: true }),
      theme,
    );

    const series = option.series[0];
    expect(series.layout).toBe("radial");
    expect(series.orient).toBe("LR");
    expect(series.orient).not.toBe("RL");
  });
});
