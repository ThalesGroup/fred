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
 * Build time windows
 */
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import dayjs, { Dayjs } from "dayjs";

// Interface for region data
export interface Region {
  name: string;
  flag: string;
  timezone: string;
}

export enum DurationPrecision {
  MINUTE = "T",
  HOUR = "H",
  DAY = "D",
  WEEK = "W",
  MONTH = "M",
  YEAR = "Y",
}

export enum Period {
  DAY1 = "1d",
  DAY2 = "2d",
  WEEK = "1w",
  MONTH = "1m",
  YEAR = "1y",
}

dayjs.extend(utc);
dayjs.extend(timezone);

// Get the date range based on the period
export const getPeriodDateRange = (period: Period): Dayjs[] => {
  const end: Dayjs = dayjs().utc();

  switch (period) {
    case Period.DAY1:
      return [end.subtract(1, "day"), end];
    case Period.DAY2:
      return [end.subtract(2, "day"), end];
    case Period.WEEK:
      return [end.subtract(1, "week"), end];
    case Period.MONTH:
      return [end.subtract(1, "month"), end];
    case Period.YEAR:
      return [end.subtract(1, "year"), end];
    default:
      return [end.subtract(1, "day"), end];
  }
};
