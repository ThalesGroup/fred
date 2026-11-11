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

import { describe, expect, it } from "vitest";
import { trendPoints } from "./kpiTrend";

const points = [
  { start: "2026-10-01", values: { messages: 4, input_tokens: 100, output_tokens: 20, co2e_grams: 300, visitors: 3 } },
  { start: "2026-10-02", values: { messages: 0, input_tokens: 0, output_tokens: 0, co2e_grams: 0, visitors: 1 } },
  { start: "2026-10-05", values: { messages: 7, input_tokens: 50, output_tokens: 5, co2e_grams: 1200, visitors: 4 } },
];
const last = (values: { values: Record<string, number> }[]) => values[values.length - 1].values.trend;

describe("trendPoints", () => {
  it("ends a running total on the period value the tile shows", () => {
    expect(trendPoints(points, "messages").map((p) => p.values.trend)).toEqual([4, 4, 11]);
    expect(last(trendPoints(points, "tokens"))).toBe(175);
    // The footprint tile shows kilograms; the series carries grams.
    expect(last(trendPoints(points, "footprint"))).toBeCloseTo(1.5);
  });

  it("keeps a distinct count per bucket, since buckets do not add up to the period", () => {
    expect(trendPoints(points, "visitors").map((p) => p.values.trend)).toEqual([3, 1, 4]);
  });

  it("keeps the bucket starts, so labels match the page charts", () => {
    expect(trendPoints(points, "messages").map((p) => p.start)).toEqual(points.map((p) => p.start));
    expect(trendPoints(undefined, "messages")).toEqual([]);
  });
});
