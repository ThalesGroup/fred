// @vitest-environment happy-dom

import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { ChartPartRenderer } from "./chartPartRenderer";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("recharts", async () => {
  const React = await import("react");
  const component = (name: string) => {
    const Mock = ({
      children,
      data,
      fill,
      stroke,
    }: {
      children?: React.ReactNode;
      data?: unknown;
      fill?: string;
      stroke?: string;
    }) =>
      React.createElement(
        "div",
        {
          "data-chart": name,
          "data-rows": data ? JSON.stringify(data) : undefined,
          "data-color": fill ?? stroke,
          "data-direct-axes": name.endsWith("Chart")
            ? React.Children.toArray(children).filter(
                (child) =>
                  React.isValidElement(child) &&
                  ["XAxis", "YAxis"].includes((child.type as { displayName?: string }).displayName ?? ""),
              ).length
            : undefined,
        },
        children,
      );
    Mock.displayName = name;
    return Mock;
  };
  return Object.fromEntries(
    [
      "Area",
      "AreaChart",
      "Bar",
      "BarChart",
      "CartesianGrid",
      "Cell",
      "Legend",
      "Line",
      "LineChart",
      "Pie",
      "PieChart",
      "ResponsiveContainer",
      "Tooltip",
      "XAxis",
      "YAxis",
    ].map((name) => [name, component(name)]),
  );
});

const rows = [
  { quarter: "A very long quarter label", sales: "12.5" },
  { quarter: "Q2", sales: null },
];

for (const chartType of ["bar", "line", "area", "pie", "table"] as const) {
  it(`renders ${chartType} with its raw source table`, () => {
    const html = renderToStaticMarkup(
      <ChartPartRenderer
        part={{ type: "chart", chart_type: chartType, title: "Sales", rows, x_key: "quarter", y_keys: ["sales"] }}
      />,
    );
    expect(html).toContain("A very long quarter label");
    expect(html).toContain("<table");
    expect(html).toContain("12.5");
    expect(html).toContain("chat.chart.data");
    if (chartType === "table") {
      expect(html).not.toContain("data-chart=");
    } else {
      expect(html).toContain(`data-chart="${chartType[0].toUpperCase() + chartType.slice(1)}Chart"`);
      expect(html).toContain("sales&quot;:12.5");
      expect(html).toContain('data-color="#4e8cff"');
      if (chartType !== "pie") expect(html).toContain('data-direct-axes="2"');
    }
  });
}

it("shows a readable fallback for malformed saved parts", () => {
  const html = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "line",
        title: "Bad",
        rows: [{ quarter: "Q1" }],
        x_key: "quarter",
        y_keys: ["sales"],
      }}
    />,
  );
  expect(html).toContain("chat.chart.unavailable");
  expect(html).not.toContain("<table");
});

it("rejects nested saved table cells and negative pie slices", () => {
  const nested = renderToStaticMarkup(
    <ChartPartRenderer part={{ type: "chart", chart_type: "table", title: "Bad", rows: [{ value: { nested: 1 } }] }} />,
  );
  const negative = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "pie",
        title: "Bad",
        rows: [{ label: "A", value: -1 }],
        x_key: "label",
        y_keys: ["value"],
      }}
    />,
  );
  const malformedKeys = renderToStaticMarkup(
    <ChartPartRenderer
      part={{ type: "chart", chart_type: "table", title: "Bad", rows: [{ value: 1 }], y_keys: "value" }}
    />,
  );
  expect(nested).toContain("chat.chart.unavailable");
  expect(negative).toContain("chat.chart.unavailable");
  expect(malformedKeys).toContain("chat.chart.unavailable");
});
