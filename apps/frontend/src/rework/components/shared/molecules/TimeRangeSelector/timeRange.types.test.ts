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

import { describe, expect, it } from "vitest";
import { canShiftForward, refreshTimeRange, resolvePreset, shiftTimeRange, startOfUnit } from "./timeRange.types";

// Wednesday 16 September 2026, 15:30 local time.
const NOW = new Date(2026, 8, 16, 15, 30);
const DAY = 24 * 60 * 60 * 1000;
const local = (y: number, m: number, d: number) => new Date(y, m, d).toISOString();

describe("startOfUnit", () => {
  it("starts weeks on Monday, including when today is Sunday", () => {
    expect(startOfUnit("week", NOW).toISOString()).toBe(local(2026, 8, 14));
    expect(startOfUnit("week", new Date(2026, 8, 20, 23, 0)).toISOString()).toBe(local(2026, 8, 14));
    expect(startOfUnit("week", new Date(2026, 8, 14, 0, 0)).toISOString()).toBe(local(2026, 8, 14));
  });

  it("moves months across a year boundary, from any day of the month", () => {
    expect(startOfUnit("month", new Date(2026, 2, 31), -1).toISOString()).toBe(local(2026, 1, 1));
    expect(startOfUnit("month", NOW, -9).toISOString()).toBe(local(2025, 11, 1));
  });
});

describe("resolvePreset", () => {
  it("covers the current calendar period up to now", () => {
    expect(resolvePreset("thisMonth", 0, NOW)).toEqual({
      since: local(2026, 8, 1),
      until: NOW.toISOString(),
      presetKey: "thisMonth",
      offset: 0,
    });
  });

  it("covers a whole past calendar period once shifted", () => {
    expect(resolvePreset("thisMonth", -1, NOW)).toMatchObject({ since: local(2026, 7, 1), until: local(2026, 8, 1) });
    expect(resolvePreset("thisWeek", -1, NOW)).toMatchObject({ since: local(2026, 8, 7), until: local(2026, 8, 14) });
    expect(resolvePreset("today", -1, NOW)).toMatchObject({ since: local(2026, 8, 15), until: local(2026, 8, 16) });
  });

  it("steps a rolling window back by its own length", () => {
    const range = resolvePreset("last30d", -1, NOW);
    expect(range.until).toBe(new Date(NOW.getTime() - 30 * DAY).toISOString());
    expect(range.since).toBe(new Date(NOW.getTime() - 60 * DAY).toISOString());
  });
});

describe("shiftTimeRange", () => {
  it("steps a preset by one period and back to the current one", () => {
    const previous = shiftTimeRange(resolvePreset("thisMonth", 0, NOW), -1, NOW);
    expect(previous).toMatchObject({ presetKey: "thisMonth", offset: -1, since: local(2026, 7, 1) });
    expect(shiftTimeRange(previous, 1, NOW)).toEqual(resolvePreset("thisMonth", 0, NOW));
  });

  it("never steps a preset into the future", () => {
    expect(shiftTimeRange(resolvePreset("last7d", 0, NOW), 1, NOW)).toMatchObject({ offset: 0 });
  });

  it("steps a custom range by its own length, stopping at now", () => {
    const custom = { since: local(2026, 7, 1), until: local(2026, 7, 11) };
    expect(shiftTimeRange(custom, -1, NOW)).toEqual({ since: local(2026, 6, 22), until: local(2026, 7, 1) });

    const recent = {
      since: new Date(NOW.getTime() - 3 * DAY).toISOString(),
      until: new Date(NOW.getTime() - DAY).toISOString(),
    };
    expect(shiftTimeRange(recent, 1, NOW)).toEqual({
      since: new Date(NOW.getTime() - 2 * DAY).toISOString(),
      until: NOW.toISOString(),
    });
  });
});

describe("canShiftForward", () => {
  it("is false only once the range reaches now", () => {
    expect(canShiftForward(resolvePreset("thisMonth", 0, NOW), NOW)).toBe(false);
    expect(canShiftForward(resolvePreset("thisMonth", -1, NOW), NOW)).toBe(true);
    expect(canShiftForward({ since: local(2026, 7, 1), until: local(2026, 7, 11) }, NOW)).toBe(true);
    expect(canShiftForward({ since: local(2026, 7, 1), until: NOW.toISOString() }, NOW)).toBe(false);
  });
});

describe("refreshTimeRange", () => {
  it("brings a current preset up to now", () => {
    const stale = resolvePreset("last7d", 0, new Date(Date.now() - DAY));
    expect(Date.parse(refreshTimeRange(stale).until)).toBeGreaterThan(Date.parse(stale.until));
  });

  it("leaves a past period and a custom range as they are", () => {
    const august = resolvePreset("thisMonth", -1, NOW);
    expect(refreshTimeRange(august)).toBe(august);
    const custom = { since: local(2026, 7, 1), until: local(2026, 7, 11) };
    expect(refreshTimeRange(custom)).toBe(custom);
  });
});
