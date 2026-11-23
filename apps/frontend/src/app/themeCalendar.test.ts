// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from "vitest";
import { startThemeCalendar } from "./themeCalendar";

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it("publishes Paris date and seconds across midnight, resumes after a clock change, and cleans up", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-12-01T22:59:58Z"));
  const stop = startThemeCalendar();
  const root = document.documentElement;
  const read = () => [root.dataset.calendarDate, root.style.getPropertyValue("--fred-seconds-since-midnight")];
  expect(read()).toEqual(["2026-12-01", "86398"]);
  vi.advanceTimersByTime(2000);
  expect(read()).toEqual(["2026-12-02", "0"]);
  vi.setSystemTime(new Date("2027-06-02T05:30:01Z"));
  document.dispatchEvent(new Event("visibilitychange"));
  expect(read()).toEqual(["2027-06-02", "27001"]);
  stop();
  window.dispatchEvent(new Event("pageshow"));
  expect(read()).toEqual([undefined, ""]);
  expect(vi.getTimerCount()).toBe(0);
});

it("samples on a hidden mount and starts ticking on return", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-12-01T22:59:58Z"));
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  const stop = startThemeCalendar();
  expect(document.documentElement.dataset.calendarDate).toBe("2026-12-01");
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(2000);
  hidden.mockReturnValue(false);
  document.dispatchEvent(new Event("visibilitychange"));
  expect(document.documentElement.dataset.calendarDate).toBe("2026-12-02");
  expect(vi.getTimerCount()).toBe(1);
  stop();
});
