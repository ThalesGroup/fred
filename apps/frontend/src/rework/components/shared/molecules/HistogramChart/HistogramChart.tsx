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

import type { LabelValuePoint } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import BarChart from "../BarChart/BarChart";

interface HistogramChartProps {
  title: string;
  rows: LabelValuePoint[];
  valueLabel?: string;
  emptyMessage?: string;
  isLoading: boolean;
  isError: boolean;
}

/**
 * A distribution over ordered buckets.
 *
 * Deliberately a thin wrapper around `BarChart` rather than its own chart: the
 * only difference is semantics, and baking them in here stops every histogram
 * call site from repeating (and eventually disagreeing on) the same three props.
 *
 * - `sortOrder="none"` — bucket order IS the x axis; re-sorting by value would
 *   destroy the distribution.
 * - `orientation="vertical"` — buckets read left-to-right along the x axis.
 * - near-contiguous bars — a histogram's bars are adjacent, unlike the gapped
 *   bars of a categorical comparison. `barCategoryGap` is the GAP, so this has
 *   to be below Recharts' `'10%'` default, not above it: a larger value would
 *   spread the buckets further apart, the opposite of what a histogram wants.
 *
 * Bucket labels come from the backend already display-ready (numeric ranges such
 * as "2-3"), so they are rendered verbatim and need no translation.
 */
export default function HistogramChart({
  title,
  rows,
  valueLabel,
  emptyMessage,
  isLoading,
  isError,
}: HistogramChartProps) {
  // A distribution preset returns every bucket even when the range is empty, so
  // "no data" arrives as a row of zeros rather than as no rows. A flat all-zero
  // axis reads as a broken chart; hand it to BarChart as empty so it shows
  // `emptyMessage` instead.
  const displayRows = rows.some((row) => row.value > 0) ? rows : [];

  return (
    <BarChart
      title={title}
      rows={displayRows}
      valueLabel={valueLabel}
      emptyMessage={emptyMessage}
      isLoading={isLoading}
      isError={isError}
      sortOrder="none"
      orientation="vertical"
      barCategoryGap="2%"
    />
  );
}
