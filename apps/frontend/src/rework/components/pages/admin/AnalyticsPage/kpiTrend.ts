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

import type { BucketPoint } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { ValueFormat } from "./analyticsFormat";

/** cumulative: a running total whose last point is the tile value. distinct: a count per bucket. */
export type TrendKind = "cumulative" | "distinct";

interface TrendDef {
  kind: TrendKind;
  /** Activity series summed into the plotted value. */
  keys: string[];
  /** Factor from the series' unit to the tile's, e.g. grams to kilograms. */
  scale?: number;
  format: ValueFormat;
}

/** Tile ids whose value has a per-bucket series in the activity preset. */
export const KPI_TRENDS = {
  conversations: { kind: "cumulative", keys: ["conversations"], format: "count" },
  messages: { kind: "cumulative", keys: ["messages"], format: "count" },
  cost: { kind: "cumulative", keys: ["cost_eur"], format: "eur" },
  tokens: { kind: "cumulative", keys: ["input_tokens", "output_tokens"], format: "compact" },
  footprint: { kind: "cumulative", keys: ["co2e_grams"], scale: 0.001, format: "decimal" },
  activeUsers: { kind: "distinct", keys: ["active_users"], format: "count" },
  visitors: { kind: "distinct", keys: ["visitors"], format: "count" },
} satisfies Record<string, TrendDef>;

export type TrendId = keyof typeof KPI_TRENDS;

export function isTrendId(id: string): id is TrendId {
  return Object.prototype.hasOwnProperty.call(KPI_TRENDS, id);
}

/** The plotted value per bucket, as single-series points for `bucketSeries`. */
export function trendPoints(points: BucketPoint[] | undefined, id: TrendId): BucketPoint[] {
  const def: TrendDef = KPI_TRENDS[id];
  let total = 0;
  return (points ?? []).map((p) => {
    const value = def.keys.reduce((sum, key) => sum + (p.values[key] ?? 0), 0) * (def.scale ?? 1);
    total += value;
    return { start: p.start, values: { trend: def.kind === "cumulative" ? total : value } };
  });
}
