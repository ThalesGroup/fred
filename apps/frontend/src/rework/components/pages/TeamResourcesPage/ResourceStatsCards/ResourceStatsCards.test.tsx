// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResourceStatsCards from "./ResourceStatsCards.tsx";
import { SERIES_COLORS } from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart.tsx";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key.split(".").pop() }),
}));

let capturedBarRows: unknown;
let capturedSizeSegments: unknown;

vi.mock("@shared/molecules/BarChart/BarChart.tsx", () => ({
  default: (props: { rows: unknown }) => {
    capturedBarRows = props.rows;
    return null;
  },
}));

vi.mock("./SizeByTypeBar.tsx", () => ({
  default: (props: { segments: unknown }) => {
    capturedSizeSegments = props.segments;
    return null;
  },
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("ResourceStatsCards", () => {
  it("zero-fills the histogram for buckets missing from the API response", () => {
    render(
      <ResourceStatsCards entries={[{ bucket: "pdf", count: 3, size_bytes: 300 }]} isLoading={false} isError={false} />,
    );
    expect(capturedBarRows).toEqual([
      { label: "pdf", value: 3 },
      { label: "text", value: 0 },
      { label: "ppt", value: 0 },
      { label: "excel", value: 0 },
      { label: "other", value: 0 },
    ]);
  });

  it("assigns each bucket its developer-specified color (orange/blue/red/green/grey), not a sequential slice", () => {
    render(
      <ResourceStatsCards
        entries={[
          { bucket: "pdf", count: 1, size_bytes: 100 },
          { bucket: "ppt", count: 1, size_bytes: 200 },
        ]}
        isLoading={false}
        isError={false}
      />,
    );

    const segments = capturedSizeSegments as { key: string; value: number; color: string }[];
    expect(segments.find((s) => s.key === "pdf")).toMatchObject({ value: 100, color: SERIES_COLORS[1] }); // orange
    expect(segments.find((s) => s.key === "text")).toMatchObject({ value: 0, color: SERIES_COLORS[0] }); // blue
    expect(segments.find((s) => s.key === "ppt")).toMatchObject({ value: 200, color: SERIES_COLORS[8] }); // red
    expect(segments.find((s) => s.key === "excel")).toMatchObject({ value: 0, color: SERIES_COLORS[2] }); // green
    expect(segments.find((s) => s.key === "other")).toMatchObject({ value: 0, color: SERIES_COLORS[9] }); // grey
  });
});
