// @vitest-environment happy-dom
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

import { afterEach, expect, it, vi } from "vitest";
import { bootTheme } from "./themeBoot.testSupport";
import { CUSTOM_UI_THEMES_CACHE_KEY, PLATFORM_UI_THEMES_CACHE_KEY } from "./uiThemes";

afterEach(() => vi.useRealTimers());

function timers() {
  return { setTimeout: window.setTimeout, clearTimeout: window.clearTimeout };
}

it("ignores retained personal theme and mode keys before authentication", () => {
  const storage: Record<string, string> = {
    "localHook:ApplicationContextProvider.uiTheme": '"cloud"',
    "localHook:ApplicationContextProvider.themeMode": '"dark"',
    [PLATFORM_UI_THEMES_CACHE_KEY]: JSON.stringify({ default_theme: "cobalt" }),
  };
  const { attributes } = bootTheme({
    storage: { getItem: (key) => storage[key] ?? null },
    prefersDark: false,
  });
  expect(attributes).toMatchObject({
    "data-ui-theme": "cobalt",
    "data-ui-base-theme": "cobalt",
    "data-theme": "light",
    "data-theme-mode": "system",
  });
});

it.each([
  ["fr-FR", "fr"],
  ["en-US", "en"],
  ["de-DE", "en"],
  [undefined, "en"],
])("sets the page language from the browser language %s before authentication", (language, expected) => {
  expect(bootTheme({ language }).element.lang).toBe(expected);
});

it("publishes the local clock before React and rolls over at local midnight in a leap year", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2028, 1, 28, 23, 59, 58));
  const { attributes, properties } = bootTheme({ now: Date, timers: timers() });
  expect(attributes["data-calendar-date"]).toBe("2028-02-28");
  expect(attributes["data-calendar-day-of-year"]).toBe("59");
  expect(properties["--fred-seconds-since-midnight"]).toBe("86398");
  vi.advanceTimersByTime(2000);
  expect(attributes["data-calendar-date"]).toBe("2028-02-29");
  expect(attributes["data-calendar-day-of-year"]).toBe("60");
  expect(properties["--fred-seconds-since-midnight"]).toBe("0");
});

it("pauses live ticks while hidden and resamples on visibility and pageshow", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 11, 1, 23, 59, 58));
  const boot = bootTheme({ now: Date, timers: timers() });
  expect(vi.getTimerCount()).toBe(1);
  boot.document.hidden = true;
  boot.document.dispatchEvent(new Event("visibilitychange"));
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(2000);
  expect(boot.attributes["data-calendar-date"]).toBe("2026-12-01");
  boot.document.hidden = false;
  boot.document.dispatchEvent(new Event("visibilitychange"));
  expect(boot.attributes["data-calendar-date"]).toBe("2026-12-02");
  vi.setSystemTime(new Date(2026, 11, 2, 17, 0, 1));
  boot.window.dispatchEvent(new Event("pageshow"));
  expect(boot.properties["--fred-seconds-since-midnight"]).toBe("61201");
  expect(vi.getTimerCount()).toBe(1);
});

it("uses a cached daylight schedule before React and shares the preview sample", () => {
  vi.useFakeTimers();
  const schedule = { sunrise: "07:30", sunset: "17:00" };
  const storage: Record<string, string> = {
    [PLATFORM_UI_THEMES_CACHE_KEY]: JSON.stringify({ default_theme: "winter" }),
    [CUSTOM_UI_THEMES_CACHE_KEY]: JSON.stringify([{ id: "winter", base: "pebble", localDaylight: schedule }]),
  };
  vi.setSystemTime(new Date(2026, 11, 1, 16, 59, 59));
  const boot = bootTheme({
    storage: { getItem: (key) => storage[key] ?? null },
    prefersDark: true,
    now: Date,
    timers: timers(),
  });
  expect(boot.attributes["data-theme"]).toBe("light");
  vi.advanceTimersByTime(1000);
  expect(boot.attributes["data-theme"]).toBe("dark");
  const changes = vi.fn();
  const unsubscribe = boot.clock.subscribe(changes);
  boot.clock.setPreview({ date: "2028-03-01", secondsSinceMidnight: 17 * 3600 });
  expect(boot.attributes["data-calendar-date"]).toBe("2028-03-01");
  expect(boot.attributes["data-calendar-day-of-year"]).toBe("61");
  expect(boot.properties["--fred-seconds-since-midnight"]).toBe("61200");
  expect(boot.clock.isScheduledDark(schedule)).toBe(true);
  vi.advanceTimersByTime(60_000);
  expect(vi.getTimerCount()).toBe(0);
  expect(changes).toHaveBeenCalledTimes(1);
  boot.clock.setPreview(null);
  expect(boot.attributes["data-calendar-date"]).toBe("2026-12-01");
  expect(boot.clock.getSnapshot().secondsSinceMidnight).toBe(61260);
  expect(vi.getTimerCount()).toBe(1);
  unsubscribe();
  vi.advanceTimersByTime(60_000);
  expect(changes).toHaveBeenCalledTimes(2);
});
