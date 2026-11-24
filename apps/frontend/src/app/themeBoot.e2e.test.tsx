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

// Before login, the boot script uses public settings and ignores personal keys.
import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { expect, it, vi } from "vitest";

const BOOT_SCRIPT = readFileSync(path.resolve(__dirname, "../../public/theme-boot.js"), "utf8");

it("ignores retained personal theme and mode keys before authentication", () => {
  const storage: Record<string, string> = {
    "localHook:ApplicationContextProvider.uiTheme": '"cloud"',
    "localHook:ApplicationContextProvider.themeMode": '"dark"',
    "localHook:ApplicationContextProvider.platformUiThemes": JSON.stringify({ default_theme: "cobalt" }),
  };
  const attributes: Record<string, string> = {};
  runInNewContext(BOOT_SCRIPT, {
    window: {
      localStorage: { getItem: (key: string) => storage[key] ?? null },
      matchMedia: () => ({ matches: false }),
    },
    document: { documentElement: { setAttribute: (name: string, value: string) => (attributes[name] = value) } },
  });
  expect(attributes).toEqual({
    "data-ui-theme": "cobalt",
    "data-ui-base-theme": "cobalt",
    "data-theme": "light",
  });
});

it.each([
  ["fr-FR", "fr"],
  ["en-US", "en"],
  ["de-DE", "en"],
  [undefined, "en"],
])("sets the page language from the browser language %s before authentication", (browser, expected) => {
  const documentElement: { lang?: string; setAttribute: () => void } = { setAttribute: () => undefined };
  runInNewContext(BOOT_SCRIPT, {
    window: {
      localStorage: { getItem: () => null },
      navigator: browser === undefined ? undefined : { language: browser },
    },
    document: { documentElement },
  });
  expect(documentElement.lang).toBe(expected);
});

it("paints a cached clock theme at local sunrise, solar noon, sunset and midnight", () => {
  const schedule = { sunrise: "07:30", sunset: "17:00" };
  const keys = {
    "localHook:ApplicationContextProvider.platformUiThemes": JSON.stringify({ default_theme: "winter" }),
    "localHook:ApplicationContextProvider.customUiThemes": JSON.stringify([
      { id: "winter", label: "Winter", base: "pebble", localDaylight: schedule },
    ]),
  };
  const target = {
    localStorage: { getItem: (key: string) => keys[key] ?? null },
    matchMedia: () => ({ matches: false }),
  } as unknown as Window;
  const element = document.createElement("html");
  vi.useFakeTimers();
  try {
    for (const [hour, minute, appearance, day, twilight, position] of [
      [0, 0, "dark", 0, 0, 1],
      [7, 30, "light", 0.5, 1, 0],
      [12, 15, "light", 1, 0, 0.5],
      [17, 0, "dark", 0.5, 1, 1],
      [18, 0, "dark", 0, 0, 1],
    ] as const) {
      vi.setSystemTime(new Date(2026, 11, 24, hour, minute));
      runInNewContext(BOOT_SCRIPT, { window: target, document: { documentElement: element }, Date });
      expect(element.getAttribute("data-ui-lighting")).toBe("clock");
      expect(element.getAttribute("data-theme")).toBe(appearance);
      expect(Number(element.style.getPropertyValue("--ui-daylight"))).toBe(day);
      expect(Number(element.style.getPropertyValue("--ui-twilight"))).toBe(twilight);
      expect(Number(element.style.getPropertyValue("--ui-sun-progress"))).toBe(position);
    }
    const clock = target.fredLocalDaylight!;
    const moon = (at: Date) => clock.sample(schedule, at).values["--ui-moon-progress"];
    expect(moon(new Date(2026, 11, 25, 0, 1)) - moon(new Date(2026, 11, 24, 23, 59))).toBeCloseTo(2 / 870);
    expect(clock.validSchedule(schedule)).toBe(true);
    for (const invalid of [
      null,
      {},
      { sunrise: "7:30", sunset: "17:00" },
      { ...schedule, extra: 0 },
      { ...schedule, sunset: "07:30" },
      { ...schedule, sunset: "24:00" },
    ]) {
      expect(clock.validSchedule(invalid)).toBe(false);
    }
  } finally {
    vi.useRealTimers();
  }
});
