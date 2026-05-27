// Copyright Thales 2025
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

import dayjs, { Dayjs, ManipulateType, OpUnitType } from "dayjs";
import utc from "dayjs/plugin/utc";

dayjs.extend(utc);

/**
 * timeAxis.ts
 *
 * Fred intent: single source of truth for time handling across dashboards.
 *
 * What lives here:
 *  - Precision types (sec|min|hour|day)
 *  - Alignment to precision (startOf/endOf, UTC)
 *  - OpenSearch fixed_interval mapping
 *  - Tick formatting
 *  - Numeric x-domain padding
 *  - Continuous bucket iteration
 *  - Precision inference from a [start,end] range
 */

export type TimePrecision = "sec" | "min" | "hour" | "day";

/** dayjs unit used to align and step buckets */
export const precisionToUnit: Record<TimePrecision, ManipulateType> = {
  sec: "second",
  min: "minute",
  hour: "hour",
  day: "day",
};

/** OpenSearch fixed_interval mapping */
export const precisionToInterval: Record<TimePrecision, string> = {
  sec: "1s",
  min: "1m",
  hour: "1h",
  day: "1d",
};

/** bucket step (ms) for padding and domain math */
export const stepMsFor = (p: TimePrecision): number =>
  p === "sec" ? 1_000 : p === "min" ? 60_000 : p === "hour" ? 3_600_000 : 86_400_000;

/** UTC tick formatter matching our dashboards */
export const formatTick = (ts: number, p: TimePrecision): string => {
  const d = dayjs.utc(ts);
  if (p === "sec") return d.format("HH:mm:ss");
  if (p === "min") return d.format("HH:mm");
  if (p === "hour") return d.format("MMM D HH:mm");
  return d.format("YYYY-MM-DD");
};

/**
 * Build a padded numeric domain so first/last points don't hug the axes.
 * If sharedDomain provided, pad that; otherwise pad [start,end].
 */
export const buildPaddedDomain = (
  p: TimePrecision,
  sharedDomain?: [number, number],
  start?: Date,
  end?: Date,
): [number, number] | ["dataMin", "dataMax"] => {
  const step = stepMsFor(p);
  if (sharedDomain) return [sharedDomain[0] - step / 2, sharedDomain[1] + step / 2];
  if (start && end) {
    const a = start.getTime();
    const b = end.getTime();
    return [a - step / 2, b + step / 2];
  }
  return ["dataMin", "dataMax"];
};

/**
 * Generate a continuous UTC series of bucket boundary timestamps (ms) from start..end.
 * Use to stitch sparse backend buckets into a uniform X axis.
 */
export const iterateBuckets = (start: Date, end: Date, p: TimePrecision): number[] => {
  const unit = precisionToUnit[p];
  const out: number[] = [];
  let cur = dayjs.utc(start).startOf(unit);
  const endUtc = dayjs.utc(end).endOf(unit);
  while (cur.isBefore(endUtc) || cur.isSame(endUtc)) {
    out.push(cur.valueOf());
    cur = cur.add(1, unit);
  }
  return out;
};

/**
 * Aligns a start and end date to the given precision (UTC).
 * Returns ISO strings so it can be fed directly to APIs.
 */
export function alignDateRangeToPrecision(start: Dayjs, end: Dayjs, precision: TimePrecision): [string, string] {
  const unit: OpUnitType = precisionToUnit[precision] as OpUnitType;
  const alignedStart = dayjs.utc(start).startOf(unit);
  const alignedEnd = dayjs.utc(end).endOf(unit);
  return [alignedStart.toISOString(), alignedEnd.toISOString()];
}

/**
 * Infer a reasonable precision for a given range. Keeps return type aligned with TimePrecision.
 */
export function getPrecisionForRange(start: Date | number, end: Date | number): TimePrecision {
  const s = typeof start === "number" ? start : (start as Date).getTime();
  const e = typeof end === "number" ? end : (end as Date).getTime();
  const diffMs = e - s;
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  const diffHours = diffMs / (1000 * 60 * 60);

  if (diffMs <= 10_000) return "sec";
  if (diffHours < 10) return "min";
  if (diffDays <= 3) return "hour";
  return "day";
}
