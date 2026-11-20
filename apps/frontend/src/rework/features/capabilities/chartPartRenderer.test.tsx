// @vitest-environment happy-dom

import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { ChartPartRenderer } from "./chartPartRenderer";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("@shared/molecules/IconButtonMenu/IconButtonMenu", async () => {
  const React = await import("react");
  return {
    default: ({
      iconButton,
      options,
    }: {
      iconButton: { icon: { type: string }; "aria-label": string };
      options: { label: string; icon: { type: string } }[];
    }) =>
      React.createElement(
        "div",
        { "data-button-icon": iconButton.icon.type, "aria-label": iconButton["aria-label"] },
        options.map((option) =>
          React.createElement("span", { key: option.label, "data-option-icon": option.icon.type }, option.label),
        ),
      ),
  };
});
vi.mock("recharts", async () => {
  const React = await import("react");
  const component = (name: string) => {
    const Mock = ({
      children,
      data,
      fill,
      stroke,
      itemStyle,
      name: seriesName,
    }: {
      children?: React.ReactNode;
      data?: unknown;
      fill?: string;
      stroke?: string;
      itemStyle?: { color?: string };
      name?: string;
    }) =>
      React.createElement(
        "div",
        {
          "data-chart": name,
          "data-rows": data ? JSON.stringify(data) : undefined,
          "data-color": fill ?? stroke,
          "data-series-name": name === "Bar" ? seriesName : undefined,
          "data-tooltip-text": name === "Tooltip" ? itemStyle?.color : undefined,
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
      "ComposedChart",
      "Funnel",
      "FunnelChart",
      "LabelList",
      "Legend",
      "Line",
      "LineChart",
      "Pie",
      "PieChart",
      "PolarAngleAxis",
      "PolarGrid",
      "PolarRadiusAxis",
      "Radar",
      "RadarChart",
      "RadialBar",
      "RadialBarChart",
      "ResponsiveContainer",
      "Scatter",
      "ScatterChart",
      "Tooltip",
      "Treemap",
      "XAxis",
      "YAxis",
    ].map((name) => [name, component(name)]),
  );
});

const rows = [
  { quarter: "A very long quarter label", sales: "12.5" },
  { quarter: "Q2", sales: null },
];

const views = {
  bar: "BarChart",
  bar_horizontal: "BarChart",
  bar_stacked: "BarChart",
  line: "LineChart",
  area: "AreaChart",
  area_stacked: "AreaChart",
  pie: "PieChart",
  donut: "PieChart",
  radar: "RadarChart",
  radial_bar: "RadialBarChart",
  funnel: "FunnelChart",
  treemap: "Treemap",
  table: null,
} as const;

for (const [chartType, chartTag] of Object.entries(views)) {
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
    expect(html).toContain('data-button-icon="download"');
    expect(html).toContain("chat.chart.downloadExcel");
    expect(html).toContain('data-option-icon="table_chart"');
    if (chartTag === null) {
      expect(html).not.toContain("data-chart=");
      expect(html).not.toContain("chat.chart.downloadPng");
    } else {
      expect(html).toContain("chat.chart.downloadPng");
      expect(html).toContain('data-option-icon="image"');
      expect(html).toContain(`data-chart="${chartTag}"`);
      expect(html).toContain("sales&quot;:12.5");
      if (chartType !== "treemap") expect(html).toContain('data-color="#4e8cff"');
      if (["pie", "donut", "radial_bar", "funnel", "treemap"].includes(chartType))
        expect(html).toContain('data-tooltip-text="var(--on-surface)"');
      else expect(html).not.toContain('data-tooltip-text="var(--on-surface)"');
      if (["bar", "bar_horizontal", "bar_stacked", "line", "area", "area_stacked"].includes(chartType))
        expect(html).toContain('data-direct-axes="2"');
    }
  });
}

it("renders composed bars and lines with different colors", () => {
  const html = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "composed",
        title: "Mixed",
        rows: [{ quarter: "Q1", sales: 12, cost: 7 }],
        x_key: "quarter",
        y_keys: ["sales", "cost"],
      }}
    />,
  );
  expect(html).toContain('data-chart="ComposedChart"');
  expect(html).toContain('data-color="#4e8cff"');
  expect(html).toContain('data-color="#f97316"');
});

it("renders numeric scatter points and rejects category x values", () => {
  const good = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "scatter",
        title: "Correlation",
        rows: [{ age: "12", score: 7 }],
        x_key: "age",
        y_keys: ["score"],
      }}
    />,
  );
  const bad = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "scatter",
        title: "Bad",
        rows: [{ age: "young", score: 7 }],
        x_key: "age",
        y_keys: ["score"],
      }}
    />,
  );
  expect(good).toContain('data-chart="ScatterChart"');
  expect(good).toContain("age&quot;:12");
  expect(bad).toContain("chat.chart.unavailable");
});

it("keeps one color per bar series across categories", () => {
  const html = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "bar",
        title: "Sales",
        rows: [
          { label: "A", value: 4 },
          { label: "B", value: 5 },
        ],
        x_key: "label",
        y_keys: ["value"],
      }}
    />,
  );
  expect(html).toContain('data-color="#4e8cff"');
  expect(html).not.toContain('data-color="#f97316"');
});

it("uses a distinct stable color for each grouped bar series", () => {
  const html = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "bar",
        title: "Comparison",
        rows: [
          { quarter: "Q1", east: 4, west: 5 },
          { quarter: "Q2", east: 6, west: 7 },
        ],
        x_key: "quarter",
        y_keys: ["east", "west"],
      }}
    />,
  );
  expect(html.match(/data-chart="Bar"/g)).toHaveLength(2);
  expect(html).toContain('data-color="#4e8cff"');
  expect(html).toContain('data-color="#f97316"');
  expect(html).not.toContain('data-chart="Cell"');
});

it("groups long-form bar rows and distinguishes groups within each category", () => {
  const rows = [
    { district: "A", kind: "civil", count: 4 },
    { district: "A", kind: "military", count: 5 },
    { district: "B", kind: "civil", count: 6 },
    { district: "B", kind: "military", count: 7 },
  ];
  for (const groupKey of ["kind", undefined]) {
    const html = renderToStaticMarkup(
      <ChartPartRenderer
        part={{
          type: "chart",
          chart_type: "bar",
          title: "Comparison",
          rows,
          x_key: "district",
          y_keys: ["count"],
          group_key: groupKey,
        }}
      />,
    );
    expect(html.match(/data-chart="Bar"/g)).toHaveLength(2);
    expect(html).toContain('data-series-name="civil"');
    expect(html).toContain('data-series-name="military"');
    expect(html).toContain('data-color="#4e8cff"');
    expect(html).toContain('data-color="#f97316"');
    expect(html).toContain(
      'data-rows="[{&quot;__chart_category&quot;:&quot;A&quot;,&quot;__chart_group_0&quot;:4,&quot;__chart_group_1&quot;:5}',
    );
    expect(html).toContain("<table");
    expect(html).toContain("kind");
  }
});

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
  expect(html).not.toContain("chat.chart.downloadExcel");
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
  const pieWithTwoSeries = renderToStaticMarkup(
    <ChartPartRenderer
      part={{
        type: "chart",
        chart_type: "pie",
        title: "Bad",
        rows: [{ label: "A", first: 1, second: 2 }],
        x_key: "label",
        y_keys: ["first", "second"],
      }}
    />,
  );
  expect(nested).toContain("chat.chart.unavailable");
  expect(negative).toContain("chat.chart.unavailable");
  expect(malformedKeys).toContain("chat.chart.unavailable");
  expect(pieWithTwoSeries).toContain("chat.chart.unavailable");
});
