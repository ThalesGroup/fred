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

// index.tsx applies the theme with the fresh platform settings before the first
// render; the provider must resolve the same theme, or the page would switch.
import { act, useContext } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { localStorageKey } from "../hooks/useLocalStorageState";
import { bootTheme } from "./themeBoot.testSupport";

const h = vi.hoisted(() => ({ platform: null as null | { default_theme?: string | null; hidden_themes?: string[] } }));
vi.mock("../common/config.tsx", () => ({ getPlatformUiThemes: () => h.platform }));

vi.mock("../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useFrontendConfigQuery: () => ({ data: undefined, refetch: () => {} }),
}));

import { setCurrentUserPreferences } from "./userPreferences";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import {
  applyResolvedTheme,
  applyThemeAttributes,
  cachePlatformUiThemes,
  PLATFORM_UI_THEMES_CACHE_KEY,
  setCustomUiThemes,
  type UiTheme,
} from "./uiThemes";

const UI_THEME_STORAGE_KEY = "ApplicationContextProvider.uiTheme";
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function providerTheme(): Promise<UiTheme> {
  let seen: UiTheme | undefined;
  function Probe() {
    seen = useContext(ApplicationContext).uiTheme;
    return null;
  }
  const root = createRoot(document.createElement("div"));
  await act(async () =>
    root.render(
      <ApplicationContextProvider>
        <Probe />
      </ApplicationContextProvider>,
    ),
  );
  await act(async () => root.unmount());
  return seen!;
}

afterEach(() => {
  window.localStorage.clear();
  h.platform = null;
  setCurrentUserPreferences({});
});

describe("theme applied before render vs provider", () => {
  const platform = { default_theme: "cobalt", hidden_themes: ["pebble"] };
  it.each([
    { name: "no choice", stored: undefined, expected: "cobalt" },
    { name: "hidden choice", stored: "pebble", expected: "cobalt" },
    { name: "offered choice", stored: "cloud", expected: "cloud" },
  ])("agree with platform settings: $name", async ({ stored, expected }) => {
    h.platform = platform;
    setCurrentUserPreferences({ ui_theme_id: stored ?? null });
    if (stored) window.localStorage.setItem(localStorageKey(UI_THEME_STORAGE_KEY), JSON.stringify(stored));
    applyResolvedTheme(platform, stored ?? null);
    expect(document.documentElement.getAttribute("data-ui-theme")).toBe(expected);
    expect(await providerTheme()).toBe(expected);
    // Resolving never rewrites the user's own choice.
    expect(window.localStorage.getItem(localStorageKey(UI_THEME_STORAGE_KEY))).toBe(
      stored ? JSON.stringify(stored) : null,
    );
  });
});

describe("platform settings cache", () => {
  it("stores the settings and drops them once the platform has none", () => {
    cachePlatformUiThemes({ default_theme: "cloud", hidden_themes: [] });
    expect(JSON.parse(window.localStorage.getItem(PLATFORM_UI_THEMES_CACHE_KEY)!)).toEqual({
      default_theme: "cloud",
      hidden_themes: [],
    });
    cachePlatformUiThemes(null);
    expect(window.localStorage.getItem(PLATFORM_UI_THEMES_CACHE_KEY)).toBeNull();
  });
});

it("keeps the scheduled appearance in sync with the live clock and scrubber while respecting manual modes", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 11, 1, 16, 59, 59));
  const boot = bootTheme({ now: Date, timers: { setTimeout: window.setTimeout, clearTimeout: window.clearTimeout } });
  window.fredThemeClock = boot.clock;
  setCustomUiThemes([
    { id: "winter", label: "Winter", base: "pebble", localDaylight: { sunrise: "07:30", sunset: "17:00" } },
  ]);
  setCurrentUserPreferences({ ui_theme_id: "winter", theme_mode: "system" });
  const element = document.documentElement;
  const root = createRoot(document.createElement("div"));

  function Probe() {
    const { uiTheme, themeMode, darkMode } = useContext(ApplicationContext);
    applyThemeAttributes(uiTheme, themeMode, darkMode);
    return null;
  }

  try {
    applyResolvedTheme(null, "winter", "system");
    expect(element.getAttribute("data-theme-mode")).toBe("system");
    expect(element.getAttribute("data-theme")).toBe("light");
    await act(async () =>
      root.render(
        <ApplicationContextProvider>
          <Probe />
        </ApplicationContextProvider>,
      ),
    );
    await act(async () => vi.advanceTimersByTime(1000));
    expect(element.getAttribute("data-theme")).toBe("dark");

    await act(async () => boot.clock.setPreview({ date: "2026-12-01", secondsSinceMidnight: 7 * 3600 + 30 * 60 }));
    expect(element.getAttribute("data-theme")).toBe("light");
    await act(async () => boot.clock.setPreview(null));
    expect(element.getAttribute("data-theme")).toBe("dark");

    await act(async () => setCurrentUserPreferences({ ui_theme_id: "winter", theme_mode: "light" }));
    expect(element.getAttribute("data-theme-mode")).toBe("light");
    expect(element.getAttribute("data-theme")).toBe("light");
    await act(async () => vi.advanceTimersByTime(60_000));
    expect(element.getAttribute("data-theme")).toBe("light");
    await act(async () => setCurrentUserPreferences({ ui_theme_id: "pebble", theme_mode: "system" }));
    expect(element.getAttribute("data-theme-mode")).toBe("system");
    expect(element.getAttribute("data-theme")).toBe("light");
    expect(boot.attributes["data-calendar-date"]).toBe("2026-12-01");
  } finally {
    await act(async () => root.unmount());
    delete window.fredThemeClock;
    setCustomUiThemes([]);
    vi.useRealTimers();
  }
});
