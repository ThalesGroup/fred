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
import { describe, expect, it } from "vitest";
import {
  bucketSeries,
  bucketSpan,
  formatBucketLabel,
  formatValue,
  isoWeek,
  periodDelta,
  teamRows,
} from "./analyticsFormat";

// Echoes the key with its options, so labels show what was interpolated.
const t = ((key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${JSON.stringify(options)}` : key) as unknown as TFunction;

describe("formatBucketLabel", () => {
  it("labels weeks by ISO week number", () => {
    expect(formatBucketLabel("2026-09-28", "week", "en", t)).toBe('rework.analytics.buckets.week:{"week":40}');
    expect(isoWeek(new Date(Date.UTC(2027, 0, 1)))).toBe(53);
    expect(isoWeek(new Date(Date.UTC(2026, 0, 1)))).toBe(1);
  });

  it("labels hours, days and months without shifting the zone of the bucket start", () => {
    expect(formatBucketLabel("2026-10-05T08:00", "hour", "en", t)).toBe("8 AM");
    expect(formatBucketLabel("2026-10-05", "day", "en", t)).toBe("10/05");
    expect(formatBucketLabel("2026-11-07", "day", "fr", t)).toBe("07/11");
    expect(formatBucketLabel("2026-10-01", "month", "fr", t)).toBe("oct.");
  });

  it("adds the day to hours and the year to months when the series crosses them", () => {
    const span = bucketSpan([{ start: "2025-10-01T00:00" }, { start: "2026-10-02T23:00" }]);
    expect(span).toEqual({ days: true, years: true });
    expect(formatBucketLabel("2026-10-05T08:00", "hour", "en", t, span)).toBe("10/05, 8 AM");
    expect(formatBucketLabel("2025-10-01", "month", "en", t, span)).toBe("Oct 25");
    expect(bucketSpan([{ start: "2026-10-05T00:00" }, { start: "2026-10-05T23:00" }])).toEqual({
      days: false,
      years: false,
    });
  });
});

describe("periodDelta", () => {
  it("shows a relative change against the previous period", () => {
    expect(periodDelta({ current: 112, previous: 100 }, "relative", t, "en")).toEqual({
      label: 'rework.analytics.delta.relative:{"value":"+12%"}',
      tone: "positive",
      direction: "up",
    });
  });

  it("shows points for rates, points a fall down and colors it good when lower is better", () => {
    expect(periodDelta({ current: 0.018, previous: 0.024 }, "points", t, "en", { lowerIsBetter: true })).toEqual({
      label: 'rework.analytics.delta.points:{"value":"-0.6"}',
      tone: "positive",
      direction: "down",
    });
  });

  it("neither colors nor signs a change that rounds to zero", () => {
    expect(periodDelta({ current: 1001, previous: 1000 }, "relative", t, "en")).toEqual({
      label: 'rework.analytics.delta.relative:{"value":"0%"}',
      tone: "neutral",
    });
    expect(periodDelta({ current: 0.10001, previous: 0.1 }, "points", t, "en")?.tone).toBe("neutral");
  });

  it("stays neutral when asked and is absent without a comparable previous value", () => {
    expect(periodDelta({ current: 5, previous: 3 }, "absolute", t, "en", { neutral: true })?.tone).toBe("neutral");
    expect(periodDelta({ current: 5, previous: 0 }, "relative", t, "en")).toBeUndefined();
    expect(periodDelta({ current: 5 }, "relative", t, "en")).toBeUndefined();
    expect(periodDelta(undefined, "relative", t, "en")).toBeUndefined();
  });
});

describe("formatValue", () => {
  it("formats euros, percents and compact counts", () => {
    expect(formatValue(3860, "eur", "en")).toBe("€3,860");
    expect(formatValue(3.45, "eur", "en")).toBe("€3.45");
    expect(formatValue(0.24, "percent", "en")).toBe("24%");
    expect(formatValue(1, "days", "en")).toBe("1 day");
    expect(formatValue(2.54, "days", "fr")).toMatch(/^2,5\sjours$/);
    expect(formatValue(412_000_000, "compact", "en")).toBe("412M");
  });
});

describe("bucketSeries", () => {
  it("maps series keys to their labels, 0 when a point lacks one", () => {
    const rows = bucketSeries(
      [{ start: "2026-09-28", values: { active_users: 3 } }],
      "week",
      { active_users: "Active", visitors: "Visitors" },
      "en",
      t,
    );
    expect(rows).toEqual([{ date: 'rework.analytics.buckets.week:{"week":40}', values: { Active: 3, Visitors: 0 } }]);
  });
});

describe("teamRows", () => {
  const catalog = [
    { team_id: "a", name: "Alpha", member_count: 10 },
    { team_id: "b", name: "Beta", member_count: 2 },
    { team_id: "c", name: "Gamma", member_count: 4 },
  ];

  it("lists every catalog team, active ones first, with share and change", () => {
    const rows = teamRows(
      [{ team_id: "b", name: "Beta", active_members: 1, messages: 30, messages_previous: 20 }],
      catalog,
      [],
    );
    expect(rows.map((r) => r.teamId)).toEqual(["b", "a", "c"]);
    expect(rows[0]).toMatchObject({ members: 2, active: 1, share: 0.5, change: 0.5 });
    expect(rows[1]).toMatchObject({ active: 0, messages: 0, change: null });
  });

  it("keeps only the selected teams under a team scope", () => {
    expect(teamRows([], catalog, ["c"]).map((r) => r.teamId)).toEqual(["c"]);
  });
});
