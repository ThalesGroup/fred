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

/**
 * Aligns a start and end date to the given precision.
 * For example, with "hour" precision, the start is rounded down to the start of the hour,
 * and the end is rounded up to the end of the hour (inclusive).
 */
import dayjs, { Dayjs, OpUnitType } from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(utc);
dayjs.extend(timezone);

const precisionToUnit: Record<"sec" | "min" | "hour" | "day", OpUnitType> = {
  sec: "second",
  min: "minute",
  hour: "hour",
  day: "day",
};

export function alignDateRangeToPrecision(
  start: Dayjs,
  end: Dayjs,
  precision: "sec" | "min" | "hour" | "day"
): [string, string] {
  const unit = precisionToUnit[precision];
  const alignedStart = dayjs.utc(start).startOf(unit);
  const alignedEnd = dayjs.utc(end).endOf(unit);
  return [alignedStart.toISOString(), alignedEnd.toISOString()];
}
