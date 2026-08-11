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

import type { HomePeriod } from "./HomePage.tsx";

/** ISO `since`/`until` window ending "now", for a home period (7/30/90 days).
 * Shape matches every KPI preset arg (`{ since, until }`). "Now" is captured at
 * call time, so callers MUST memoise on `period` (a fresh `until` every render
 * would change the RTK Query cache key and refetch in a loop). */
export function homePeriodRange(period: HomePeriod): { since: string; until: string } {
  const until = new Date();
  const since = new Date(until.getTime() - period * 24 * 60 * 60 * 1000);
  return { since: since.toISOString(), until: until.toISOString() };
}

const nf = (maximumFractionDigits: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits });

/** Compact French token count: `280 k`, `1,2 M`, `640`. */
export function formatCompactTokens(n: number): string {
  if (n >= 1_000_000) return `${nf(1).format(n / 1_000_000)} M`;
  if (n >= 1_000) return `${nf(0).format(Math.round(n / 1_000))} k`;
  return nf(0).format(n);
}
