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

import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { describe, expect, it } from "vitest";
import { localStorageKey } from "../hooks/useLocalStorageState";
import {
  computeDarkMode,
  offeredUiThemes,
  PLATFORM_UI_THEMES_CACHE_KEY,
  CUSTOM_UI_THEMES_CACHE_KEY,
  availableUiThemes,
  setCustomUiThemes,
  uiThemeBase,
  uiThemeTab,
  type PlatformUiThemes,
  resolveUiTheme,
  UI_THEMES,
} from "./uiThemes";

const BOOT_SCRIPT = readFileSync(path.resolve(__dirname, "../../public/theme-boot.js"), "utf8");
const THEMES_DIR = path.resolve(__dirname, "../styles/themes");

/** Runs public/theme-boot.js against a fake browser and returns the attributes it set. */
function boot(
  storage: Record<string, string> | "unavailable",
  prefersDark: boolean | "unsupported",
): Record<string, string> {
  const attributes: Record<string, string> = {};
  const localStorage = {
    getItem: (key: string) => {
      if (storage === "unavailable") throw new Error("SecurityError");
      return key in storage ? storage[key] : null;
    },
  };
  runInNewContext(BOOT_SCRIPT, {
    window:
      prefersDark === "unsupported" ? { localStorage } : { localStorage, matchMedia: () => ({ matches: prefersDark }) },
    document: { documentElement: { setAttribute: (name: string, value: string) => (attributes[name] = value) } },
  });
  return attributes;
}

describe("UI theme catalog", () => {
  it("matches the boot script's copy", () => {
    const match = BOOT_SCRIPT.match(/var THEMES = (\[[^\]]*\]);/);
    expect(match).not.toBeNull();
    expect(JSON.parse(match![1])).toEqual([...UI_THEMES]);
  });

  it("reads public catalog settings but not personal browser choices", () => {
    expect(BOOT_SCRIPT).not.toContain(`"${localStorageKey(UI_THEME_STORAGE_KEY)}"`);
    expect(BOOT_SCRIPT).not.toContain(`"${localStorageKey(THEME_MODE_STORAGE_KEY)}"`);
    expect(BOOT_SCRIPT).toContain(`"${PLATFORM_UI_THEMES_CACHE_KEY}"`);
    expect(BOOT_SCRIPT).toContain(`"${CUSTOM_UI_THEMES_CACHE_KEY}"`);
  });

  it("matches the theme files", () => {
    const files = readdirSync(THEMES_DIR)
      .filter((f) => f.endsWith(".css"))
      .map((f) => f.replace(/\.css$/, ""));
    expect(files.sort()).toEqual([...UI_THEMES].sort());
  });
});

describe("public theme resolution before authentication", () => {
  const cases: { name: string; theme?: unknown; mode?: unknown; platform?: unknown; prefersDark: boolean }[] = [
    { name: "stored cloud, dark", theme: "cloud", mode: "dark", prefersDark: false },
    { name: "stored cobalt, light", theme: "cobalt", mode: "light", prefersDark: true },
    { name: "unknown theme", theme: "corporate", mode: "light", prefersDark: false },
    { name: "nothing stored, OS dark", prefersDark: true },
    { name: "nothing stored, OS light", prefersDark: false },
    { name: "system mode, OS dark", theme: "pebble", mode: "system", prefersDark: true },
    { name: "garbage values", theme: 42, mode: "blue", prefersDark: true },
    { name: "platform default, no choice", platform: { default_theme: "cobalt" }, prefersDark: false },
    { name: "choice wins over default", theme: "cloud", platform: { default_theme: "cobalt" }, prefersDark: false },
    {
      name: "hidden choice",
      theme: "cloud",
      platform: { default_theme: "cobalt", hidden_themes: ["cloud"] },
      prefersDark: false,
    },
    { name: "hidden default", platform: { default_theme: "pebble", hidden_themes: ["pebble"] }, prefersDark: true },
    { name: "unknown default", platform: { default_theme: "aurora" }, prefersDark: true },
    {
      name: "everything hidden",
      theme: "cloud",
      platform: { hidden_themes: ["pebble", "cobalt", "cloud"] },
      prefersDark: false,
    },
    { name: "malformed platform cache", theme: "cobalt", platform: { hidden_themes: "pebble" }, prefersDark: false },
    { name: "non-object platform cache", platform: "cobalt", prefersDark: false },
  ];

  it.each(cases)("boot script and React agree: $name", ({ theme, mode, platform, prefersDark }) => {
    const storage: Record<string, string> = {};
    if (platform !== undefined) storage[PLATFORM_UI_THEMES_CACHE_KEY] = JSON.stringify(platform);
    if (theme !== undefined) storage[localStorageKey(UI_THEME_STORAGE_KEY)] = JSON.stringify(theme);
    if (mode !== undefined) storage[localStorageKey(THEME_MODE_STORAGE_KEY)] = JSON.stringify(mode);
    const attributes = boot(storage, prefersDark);
    const parsed = typeof platform === "object" && platform !== null ? (platform as PlatformUiThemes) : null;
    expect(attributes["data-ui-theme"]).toBe(resolveUiTheme(null, parsed));
    expect(attributes["data-ui-base-theme"]).toBe(uiThemeBase(attributes["data-ui-theme"]));
    const dark = computeDarkMode("system", prefersDark);
    expect(attributes["data-theme"]).toBe(dark ? "dark" : "light");
  });

  it("falls back to the default theme and the OS mode when storage is unavailable", () => {
    expect(boot("unavailable", true)).toEqual({
      "data-ui-theme": "pebble",
      "data-ui-base-theme": "pebble",
      "data-theme": "dark",
    });
  });

  it("uses light when the browser has no matchMedia, as React does", () => {
    expect(boot({}, "unsupported")).toEqual({
      "data-ui-theme": "pebble",
      "data-ui-base-theme": "pebble",
      "data-theme": "light",
    });
  });

  it("ignores an unknown stored theme", () => {
    expect(resolveUiTheme("corporate")).toBe("pebble");
    expect(boot({ [localStorageKey(UI_THEME_STORAGE_KEY)]: JSON.stringify("corporate") }, false)["data-ui-theme"]).toBe(
      "pebble",
    );
  });
});

it("offers multiple ZIP themes and applies each inherited base before paint", () => {
  const custom = [
    { id: "acme", label: "Acme", base: "pebble" as const },
    { id: "delta", label: "Delta", base: "cloud" as const },
  ];
  setCustomUiThemes(custom);
  try {
    expect(availableUiThemes()).toEqual([...UI_THEMES, "acme", "delta"]);
    expect(resolveUiTheme(null, { default_theme: "delta" })).toBe("delta");
    expect(resolveUiTheme("acme", { hidden_themes: ["acme"] })).toBe("pebble");
    expect(
      boot(
        {
          [CUSTOM_UI_THEMES_CACHE_KEY]: JSON.stringify(custom),
          [PLATFORM_UI_THEMES_CACHE_KEY]: JSON.stringify({ default_theme: "delta" }),
          [localStorageKey(UI_THEME_STORAGE_KEY)]: JSON.stringify("delta"),
        },
        false,
      ),
    ).toMatchObject({ "data-ui-theme": "delta", "data-ui-base-theme": "cloud" });
  } finally {
    setCustomUiThemes([]);
  }
});

it("retains the validated catalog and selected theme across Vite hot-module replacement", () => {
  const source = readFileSync(path.resolve(__dirname, "uiThemes.ts"), "utf8");
  const runtime = transpileModule(source, {
    compilerOptions: { module: ModuleKind.ESNext, target: ScriptTarget.ES2022 },
  })
    .outputText.replace(/^import .*;$/gm, "")
    .replaceAll("import.meta.hot", "hot")
    .replaceAll("export ", "");
  const data: Record<string, unknown> = {};
  let dispose: (data: Record<string, unknown>) => void = () => {};
  const load = () => {
    const context = {
      localStorageKey,
      hot: {
        data,
        dispose: (callback: typeof dispose) => {
          dispose = callback;
        },
      },
    };
    return runInNewContext(`${runtime}\n({setCustomUiThemes, resolveUiTheme, offeredUiThemes, uiThemeBase});`, context);
  };
  const original = load();
  original.setCustomUiThemes([{ id: "paris-aeroport", label: "Paris Aeroport", base: "cobalt" }]);
  dispose(data);
  const refreshed = load();
  const platform = { default_theme: "paris-aeroport", hidden_themes: [...UI_THEMES] };
  expect(Array.from(refreshed.offeredUiThemes(platform))).toEqual(["paris-aeroport"]);
  expect(refreshed.resolveUiTheme("paris-aeroport", platform)).toBe("paris-aeroport");
  expect(refreshed.uiThemeBase("paris-aeroport")).toBe("cobalt");
});

it("brands the tab from the active ZIP theme and restores the app's branding", () => {
  setCustomUiThemes([
    { id: "acme", label: "Acme", base: "cobalt", tabTitle: "Acme", faviconName: "acme", faviconNameDark: "acme-dark" },
    { id: "single", label: "Single", base: "cloud", faviconName: "single" },
  ]);
  const tab = (id: string, dark: boolean) => uiThemeTab(id, dark, "App", "app", "app-dark");
  expect([tab("acme", false), tab("acme", true)]).toEqual([
    { title: "Acme", icon: "acme" },
    { title: "Acme", icon: "acme-dark" },
  ]);
  expect(tab("single", true)).toEqual({ title: "App", icon: "single" });
  expect([tab("pebble", false), tab("pebble", true)]).toEqual([
    { title: "App", icon: "app" },
    { title: "App", icon: "app-dark" },
  ]);
  setCustomUiThemes([]);
});

describe("resolveUiTheme with platform settings", () => {
  it("offers every shipped theme when nothing is hidden", () => {
    expect(offeredUiThemes(null)).toEqual([...UI_THEMES]);
  });

  it("drops hidden themes, unless that would leave none", () => {
    expect(offeredUiThemes({ hidden_themes: ["pebble"] })).toEqual(["cobalt", "cloud"]);
    expect(offeredUiThemes({ hidden_themes: [...UI_THEMES] })).toEqual([...UI_THEMES]);
  });

  it("keeps the user's offered choice", () => {
    expect(resolveUiTheme("cloud", { default_theme: "cobalt" })).toBe("cloud");
  });

  it("falls back to the platform default when the choice is hidden or absent", () => {
    expect(resolveUiTheme("cloud", { default_theme: "cobalt", hidden_themes: ["cloud"] })).toBe("cobalt");
    expect(resolveUiTheme(null, { default_theme: "cobalt" })).toBe("cobalt");
  });

  it("falls back to the first offered theme when the default is unset, hidden or unknown", () => {
    expect(resolveUiTheme(null, { hidden_themes: ["pebble"] })).toBe("cobalt");
    expect(resolveUiTheme(null, { default_theme: "aurora" })).toBe("pebble");
    expect(resolveUiTheme(null, null)).toBe("pebble");
  });
});
const UI_THEME_STORAGE_KEY = "ApplicationContextProvider.uiTheme";
const THEME_MODE_STORAGE_KEY = "ApplicationContextProvider.themeMode";
