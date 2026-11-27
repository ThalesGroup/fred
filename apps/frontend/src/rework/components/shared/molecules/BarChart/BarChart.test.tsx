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

import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("recharts", () => {
  const container = ({ children }: { children: ReactNode }) => <>{children}</>;
  return {
    ResponsiveContainer: container,
    BarChart: container,
    Bar: container,
    CartesianGrid: () => null,
    XAxis: ({ type, tickFormatter }: { type: string; tickFormatter?: (value: number) => string }) =>
      type === "number" ? <span data-axis-value={tickFormatter?.(234_400) ?? "unformatted"} /> : null,
    YAxis: ({ type, tickFormatter }: { type: string; tickFormatter?: (value: number) => string }) =>
      type === "number" ? <span data-axis-value={tickFormatter?.(234_400) ?? "unformatted"} /> : null,
    Tooltip: ({ formatter }: { formatter: (value: number) => (string | number)[] }) => (
      <span data-hover-value={formatter(987_264_624)[0]} />
    ),
    LabelList: () => null,
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));

import BarChart from "./BarChart";

const rows = [{ label: "Agent", value: 987_264_624 }];
const compact = (value: number) =>
  new Intl.NumberFormat("fr", { notation: "compact", maximumFractionDigits: 1 }).format(value);

describe("BarChart", () => {
  it.each(["horizontal", "vertical"] as const)("formats the %s token scale and hover value", (orientation) => {
    const html = renderToStaticMarkup(
      <BarChart
        title="Tokens"
        rows={rows}
        orientation={orientation}
        formatValue={compact}
        isLoading={false}
        isError={false}
      />,
    );
    expect(html).toMatch(/data-axis-value="234,4\s*k"/);
    expect(html).toMatch(/data-hover-value="987,3\s*M"/);
  });

  it("preserves the default formatting for other charts", () => {
    const html = renderToStaticMarkup(<BarChart title="Count" rows={rows} isLoading={false} isError={false} />);
    expect(html).toContain('data-axis-value="unformatted"');
    expect(html).toContain('data-hover-value="987264624"');
  });
});
