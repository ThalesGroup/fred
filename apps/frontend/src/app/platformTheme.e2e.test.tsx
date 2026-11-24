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
import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { act, useContext, type ContextType } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { localStorageKey } from "../hooks/useLocalStorageState";

const h = vi.hoisted(() => ({ platform: null as null | { default_theme?: string | null; hidden_themes?: string[] } }));
vi.mock("../common/config.tsx", () => ({ getPlatformUiThemes: () => h.platform }));

vi.mock("../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useFrontendConfigQuery: () => ({ data: undefined, refetch: () => {} }),
}));

import { setCurrentUserPreferences } from "./userPreferences";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import { applyResolvedTheme, cachePlatformUiThemes, PLATFORM_UI_THEMES_CACHE_KEY, setCustomUiThemes } from "./uiThemes";

const UI_THEME_STORAGE_KEY = "ApplicationContextProvider.uiTheme";
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
const container = document.createElement("div");
beforeEach(() => {
  root = createRoot(container);
});

function mountProvider() {
  let context: ContextType<typeof ApplicationContext>;
  function Probe() {
    context = useContext(ApplicationContext);
    return <input key={String(context.darkMode)} />;
  }
  act(() =>
    root.render(
      <ApplicationContextProvider>
        <Probe />
      </ApplicationContextProvider>,
    ),
  );
  return () => context;
}

afterEach(() => {
  act(() => root.unmount());
  setCustomUiThemes([]);
  delete window.fredLocalDaylight;
  vi.restoreAllMocks();
  vi.useRealTimers();
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
  ])("agree with platform settings: $name", ({ stored, expected }) => {
    h.platform = platform;
    setCurrentUserPreferences({ ui_theme_id: stored ?? null });
    if (stored) window.localStorage.setItem(localStorageKey(UI_THEME_STORAGE_KEY), JSON.stringify(stored));
    applyResolvedTheme(platform, stored ?? null);
    expect(document.documentElement.getAttribute("data-ui-theme")).toBe(expected);
    const context = mountProvider();
    expect(context().uiTheme).toBe(expected);
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

it("updates the visible clock, resumes after sleep, and releases it when the mode or theme changes", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 11, 24, 16, 59, 59));
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  const boot = readFileSync(path.resolve(__dirname, "../../public/theme-boot.js"), "utf8");
  runInNewContext(boot, { window, document, Date });
  const localDaylight = { sunrise: "07:30", sunset: "17:00" };
  setCustomUiThemes([{ id: "winter", label: "Winter", base: "pebble", localDaylight }]);
  h.platform = { default_theme: "winter" };
  applyResolvedTheme(h.platform);
  const element = document.documentElement;
  expect(element.dataset.theme).toBe("light");
  const context = mountProvider();
  expect(context().darkMode).toBe(false);
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(context().darkMode).toBe(true);
  expect(element.style.getPropertyValue("--ui-twilight")).toBe("1");

  const setHidden = (value: boolean) => {
    hidden.mockReturnValue(value);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
  };
  setHidden(true);
  vi.setSystemTime(new Date(2026, 11, 25, 12, 15));
  setHidden(false);
  expect(context().darkMode).toBe(false);
  expect(element.style.getPropertyValue("--ui-sun-progress")).toBe("0.5");

  const select = (ui_theme_id: string, theme_mode: "dark" | "light" | "system") =>
    act(() => setCurrentUserPreferences({ ui_theme_id, theme_mode }));
  select("winter", "dark");
  expect(context().darkMode).toBe(true);
  expect(element.hasAttribute("data-ui-lighting")).toBe(false);
  expect(element.style.getPropertyValue("--ui-daylight")).toBe("");
  vi.setSystemTime(new Date(2026, 11, 25, 23, 30));
  select("winter", "light");
  expect(context().darkMode).toBe(false);
  select("winter", "system");
  expect(context().darkMode).toBe(true);
  select("pebble", "system");
  expect(element.hasAttribute("data-ui-lighting")).toBe(false);
  expect(context().darkMode).toBe(window.matchMedia("(prefers-color-scheme: dark)").matches);

  // The wiki editor is keyed by mode. Switching between two light themes must preserve its DOM.
  const editor = container.firstChild;
  vi.setSystemTime(new Date(2026, 11, 26, 12));
  select("winter", "system");
  expect(context().darkMode).toBe(false);
  expect(container.firstChild).toBe(editor);
});
