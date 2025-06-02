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

import dayjs from "dayjs";
import duration from "dayjs/plugin/duration";

dayjs.extend(duration);

function parseDuration(durationString: string): string {
  const units: { [key: string]: string } = {
    m: "minute",
    h: "hour",
    d: "day",
    w: "week",
    M: "month",
  };

  const value = parseInt(durationString.slice(0, -1));
  const unit = durationString.slice(-1);

  if (isNaN(value) || !units[unit]) {
    return "Invalid duration";
  }

  const unitName = units[unit];
  return `${value} ${unitName}${value !== 1 ? "s" : ""}`;
}

export function formatDuration(durationString: string): string {
  const parts = durationString.trim().split(/\s+/);
  const formattedParts = parts.map((part) => parseDuration(part));
  const validParts = formattedParts.filter((part) => part !== "Invalid duration");

  if (validParts.length === 0) {
    return "Invalid duration";
  }
  if (validParts.length === 1) {
    return validParts[0];
  } else {
    const lastPart = validParts.pop();
    return `${validParts.join(", ")} and ${lastPart}`;
  }
}

export function addDurationToDate(startDate: Date | string, durationString: string): Date {
  const start = dayjs(startDate);
  const durationRegex = /^(\d)+([smhdwMy])$/;
  const match = durationString.match(durationRegex);

  if (!match) {
    throw new Error('Invalid duration format. Use format like "1d", "30m", "2h".');
  }

  const [, amount, unit] = match;
  let durationObject: duration.Duration;

  switch (unit) {
    case "s":
      durationObject = dayjs.duration({ seconds: parseInt(amount) });
      break;
    case "d":
      durationObject = dayjs.duration({ days: parseInt(amount) });
      break;
    case "h":
      durationObject = dayjs.duration({ hours: parseInt(amount) });
      break;
    case "m":
      durationObject = dayjs.duration({ minutes: parseInt(amount) });
      break;
    case "w":
      durationObject = dayjs.duration({ weeks: parseInt(amount) });
      break;
    case "M":
      durationObject = dayjs.duration({ months: parseInt(amount) });
      break;
    default:
      throw new Error(
        'Invalid duration unit. Use "d" for days, "h" for hours, or "m" for minutes, "w" for weeks, "M" for months.',
      );
  }

  return start.add(durationObject).toDate();
}
