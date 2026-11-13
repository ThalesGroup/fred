// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { afterEach, expect, it, vi } from "vitest";
import { homePeriodRange } from "./homePeriod";

afterEach(() => vi.useRealTimers());

it.each([7, 30, 90] as const)("includes recent activity in a %s-day window without rounding its end", (period) => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-13T06:09:14.392Z"));
  const range = homePeriodRange(period);
  expect(range.until).toBe("2026-11-13T06:09:14.392Z");
  expect(Date.parse(range.until) - Date.parse(range.since)).toBe(period * 86400000);
  for (const created of ["2026-11-13T06:07:16.916Z", "2026-11-13T06:09:03.136Z"])
    expect(Date.parse(created)).toBeLessThan(Date.parse(range.until));
  vi.setSystemTime(new Date("2026-11-13T06:09:40.000Z"));
  expect(homePeriodRange(period).until).toBe("2026-11-13T06:09:40.000Z");
});
