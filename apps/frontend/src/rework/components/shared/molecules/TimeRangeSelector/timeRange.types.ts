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

export type TimePresetKey =
  | "last15m"
  | "last1h"
  | "last6h"
  | "last24h"
  | "last7d"
  | "last30d"
  | "today"
  | "thisWeek"
  | "thisMonth";

export interface TimeRange {
  since: string;
  until: string;
  presetKey?: TimePresetKey;
}

export interface TimePreset {
  key: TimePresetKey;
  labelKey: string;
  resolve: () => { since: string; until: string };
}

function isoNow() {
  return new Date().toISOString();
}

function isoMinus(ms: number) {
  return new Date(Date.now() - ms).toISOString();
}

function startOf(unit: "day" | "week" | "month") {
  const d = new Date();
  if (unit === "day") {
    d.setHours(0, 0, 0, 0);
  } else if (unit === "week") {
    const day = d.getDay();
    d.setDate(d.getDate() - day);
    d.setHours(0, 0, 0, 0);
  } else {
    d.setDate(1);
    d.setHours(0, 0, 0, 0);
  }
  return d.toISOString();
}

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

export const TIME_PRESETS: TimePreset[] = [
  {
    key: "last15m",
    labelKey: "rework.analytics.presets.last15m",
    resolve: () => ({ since: isoMinus(15 * MIN), until: isoNow() }),
  },
  {
    key: "last1h",
    labelKey: "rework.analytics.presets.last1h",
    resolve: () => ({ since: isoMinus(HOUR), until: isoNow() }),
  },
  {
    key: "last6h",
    labelKey: "rework.analytics.presets.last6h",
    resolve: () => ({ since: isoMinus(6 * HOUR), until: isoNow() }),
  },
  {
    key: "last24h",
    labelKey: "rework.analytics.presets.last24h",
    resolve: () => ({ since: isoMinus(DAY), until: isoNow() }),
  },
  {
    key: "last7d",
    labelKey: "rework.analytics.presets.last7d",
    resolve: () => ({ since: isoMinus(7 * DAY), until: isoNow() }),
  },
  {
    key: "last30d",
    labelKey: "rework.analytics.presets.last30d",
    resolve: () => ({ since: isoMinus(30 * DAY), until: isoNow() }),
  },
  {
    key: "today",
    labelKey: "rework.analytics.presets.today",
    resolve: () => ({ since: startOf("day"), until: isoNow() }),
  },
  {
    key: "thisWeek",
    labelKey: "rework.analytics.presets.thisWeek",
    resolve: () => ({ since: startOf("week"), until: isoNow() }),
  },
  {
    key: "thisMonth",
    labelKey: "rework.analytics.presets.thisMonth",
    resolve: () => ({ since: startOf("month"), until: isoNow() }),
  },
];
