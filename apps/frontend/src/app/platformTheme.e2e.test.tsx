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

const h = vi.hoisted(() => ({ platform: null as null | { default_theme?: string | null; hidden_themes?: string[] } }));
vi.mock("../common/config.tsx", () => ({ getPlatformUiThemes: () => h.platform }));

import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import {
  applyResolvedTheme,
  cachePlatformUiThemes,
  PLATFORM_UI_THEMES_CACHE_KEY,
  UI_THEME_STORAGE_KEY,
  type UiTheme,
} from "./uiThemes";

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
});

describe("theme applied before render vs provider", () => {
  const platform = { default_theme: "cobalt", hidden_themes: ["pebble"] };
  it.each([
    { name: "no choice", stored: undefined, expected: "cobalt" },
    { name: "hidden choice", stored: "pebble", expected: "cobalt" },
    { name: "offered choice", stored: "cloud", expected: "cloud" },
  ])("agree with platform settings: $name", async ({ stored, expected }) => {
    h.platform = platform;
    if (stored) window.localStorage.setItem(localStorageKey(UI_THEME_STORAGE_KEY), JSON.stringify(stored));
    applyResolvedTheme(platform);
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
