// @vitest-environment happy-dom

import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { ChartPartRenderer } from "./chartPartRenderer";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("@shared/molecules/IconButtonMenu/IconButtonMenu", () => ({ default: () => null }));
vi.mock("recharts", async (importOriginal) => {
  const React = await import("react");
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement<{ width?: number; height?: number }> }) =>
      React.cloneElement(children, { width: 640, height: 320 }),
  };
});

const views = [
  "bar",
  "bar_horizontal",
  "bar_stacked",
  "line",
  "area",
  "area_stacked",
  "pie",
  "donut",
  "scatter",
  "radar",
  "radial_bar",
  "funnel",
  "treemap",
  "composed",
] as const;

for (const chartType of views) {
  it(`renders a real Recharts ${chartType} SVG`, () => {
    const rows =
      chartType === "scatter"
        ? [
            { label: 1, value: 4, other: 2 },
            { label: 2, value: 8, other: 5 },
          ]
        : [
            { label: "A", value: 4, other: 2 },
            { label: "B", value: 8, other: 5 },
          ];
    const html = renderToStaticMarkup(
      <ChartPartRenderer
        part={{
          type: "chart",
          chart_type: chartType,
          title: "Sample",
          rows,
          x_key: "label",
          y_keys: chartType === "composed" ? ["value", "other"] : ["value"],
        }}
      />,
    );
    expect(html).toContain("<svg");
    expect(html).not.toContain("chat.chart.unavailable");
    if (["radial_bar", "funnel", "treemap"].includes(chartType)) {
      const svg = html.slice(html.indexOf("<svg"), html.lastIndexOf("</svg>") + 6);
      expect(svg).toContain(">A<");
      expect(svg).toContain(">B<");
    }
  });
}

it("renders distinct Recharts bar colors for long-form groups", () => {
  const html = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "bar",
        title: "Comparison",
        rows: [
          { district: "A", kind: "civil", count: 4 },
          { district: "A", kind: "military", count: 5 },
          { district: "B", kind: "civil", count: 6 },
          { district: "B", kind: "military", count: 7 },
        ],
        x_key: "district",
        y_keys: ["count"],
        group_key: "kind",
      }}
    />,
  );
  const svg = html.slice(html.indexOf("<svg"), html.lastIndexOf("</svg>") + 6);
  expect(svg).toContain('fill="#4e8cff"');
  expect(svg).toContain('fill="#f97316"');
  expect(html).toContain("civil</span>");
  expect(html).toContain("military</span>");
});
