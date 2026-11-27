// Copyright Thales 2026
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

// Focus: the empty state. A settled query with no rows used to render the
// title and nothing else, which on the Analytics page reads as a chart that
// failed to draw. The trend presets make that routine - they emit a sparse
// series and drop the current partial bucket, so a range whose only activity
// is in that bucket has no point to plot at all.

import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("recharts", () => {
  const container = ({ children }: { children: ReactNode }) => <>{children}</>;
  return {
    ResponsiveContainer: container,
    LineChart: container,
    CartesianGrid: () => null,
    XAxis: () => null,
    Line: () => null,
    YAxis: ({ tickFormatter }: { tickFormatter: (value: number) => string }) => (
      <span data-axis-ticks={`${tickFormatter(1_000)},${tickFormatter(234_400)},${tickFormatter(1_000_000)}`} />
    ),
    Tooltip: ({ formatter }: { formatter: (value: number) => (string | number)[] }) => (
      <span data-hover-value={formatter(1_234_567)[0]} />
    ),
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));

import TimeSeriesLineChart from "./TimeSeriesLineChart";

const settled = { isFetching: false, isLoading: false, isError: false };

describe("TimeSeriesLineChart", () => {
  it("falls back to the shared no-data message when no emptyMessage is given", () => {
    const html = renderToStaticMarkup(<TimeSeriesLineChart title="Sessions" rows={[]} {...settled} />);
    expect(html).toContain("common.noData");
  });

  it("prefers the caller's emptyMessage", () => {
    const html = renderToStaticMarkup(
      <TimeSeriesLineChart title="Depth" rows={[]} emptyMessage="nothing.to.trend" {...settled} />,
    );
    expect(html).toContain("nothing.to.trend");
    expect(html).not.toContain("common.noData");
  });

  it("stays on the loading state while a refetch is in flight", () => {
    const html = renderToStaticMarkup(
      <TimeSeriesLineChart title="Depth" rows={[]} emptyMessage="nothing.to.trend" {...settled} isFetching />,
    );
    expect(html).toContain("common.loading");
    expect(html).not.toContain("nothing.to.trend");
  });

  it("shows the error state alone when the query failed", () => {
    const html = renderToStaticMarkup(
      <TimeSeriesLineChart title="Depth" rows={[]} emptyMessage="nothing.to.trend" {...settled} isError />,
    );
    expect(html).toContain("common.loadingError");
    expect(html).not.toContain("nothing.to.trend");
  });

  it("shows the loading state alone on a first load", () => {
    const html = renderToStaticMarkup(
      <TimeSeriesLineChart title="Depth" rows={[]} emptyMessage="nothing.to.trend" {...settled} isLoading />,
    );
    expect(html).toContain("common.loading");
    expect(html).not.toContain("nothing.to.trend");
  });

  it("shows no empty state once there is a point to plot", () => {
    const html = renderToStaticMarkup(
      <TimeSeriesLineChart title="Depth" rows={[{ date: "2026-08-26", value: 2 }]} {...settled} />,
    );
    expect(html).not.toContain("common.noData");
  });

  it("abbreviates the token scale and hovered value", () => {
    const html = renderToStaticMarkup(
      <TimeSeriesLineChart title="Tokens" rows={[{ date: "2026-08-26", value: 1_234_567 }]} {...settled} />,
    );
    expect(html).toMatch(/data-axis-ticks="1\s*k,234,4\s*k,1\s*M"/);
    expect(html).toMatch(/data-hover-value="1,2\s*M"/);
  });
});
