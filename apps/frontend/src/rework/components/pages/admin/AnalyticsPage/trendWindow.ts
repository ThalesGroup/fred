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

import type { TFunction } from "i18next";

// The trailing window of a trend preset (#2428) arrives in the same compact
// form as `interval` — "7d" for seven daily buckets, "7h" for hourly ones — and
// the backend resolves it from the bucket size, so it is not a constant this
// side may assume (`kpi/utils.py`, resolve_trend_interval). Splitting the count
// from the unit letter here is what keeps "7-day" out of the translation
// catalog: the count is interpolated, the unit picks the phrase.
const UNIT_KEYS: Record<string, string> = {
  s: "second",
  m: "minute",
  h: "hour",
  d: "day",
};

/**
 * Localized name of a trailing window ("trailing 7 days" / "7 jours glissants").
 *
 * Returns undefined while the response has not arrived yet, or for a unit this
 * frontend does not know — the caller then drops the label entirely rather than
 * rendering a half-built sentence.
 */
export function formatTrendWindow(window: string | null | undefined, t: TFunction): string | undefined {
  if (!window) return undefined;
  const unit = UNIT_KEYS[window.slice(-1)];
  const count = Number(window.slice(0, -1));
  if (!unit || !Number.isFinite(count)) return undefined;
  return t(`rework.analytics.engagement.trendWindow.${unit}`, { count });
}
