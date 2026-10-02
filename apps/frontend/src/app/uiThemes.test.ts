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
import { describe, expect, it } from "vitest";
import { computeDarkMode } from "./ApplicationContextProvider";
import { localStorageKey } from "../hooks/useLocalStorageState";
import { resolveUiTheme, THEME_MODE_STORAGE_KEY, UI_THEME_STORAGE_KEY, UI_THEMES } from "./uiThemes";
import type { ThemeMode } from "./ApplicationContextStruct";

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

  it("reads the keys the storage hook writes", () => {
    expect(BOOT_SCRIPT).toContain(`"${localStorageKey(UI_THEME_STORAGE_KEY)}"`);
    expect(BOOT_SCRIPT).toContain(`"${localStorageKey(THEME_MODE_STORAGE_KEY)}"`);
  });

  it("matches the theme files", () => {
    const files = readdirSync(THEMES_DIR)
      .filter((f) => f.endsWith(".css"))
      .map((f) => f.replace(/\.css$/, ""));
    expect(files.sort()).toEqual([...UI_THEMES].sort());
  });
});

describe("theme resolution before the first paint", () => {
  const cases: { name: string; theme?: unknown; mode?: unknown; prefersDark: boolean }[] = [
    { name: "stored cloud, dark", theme: "cloud", mode: "dark", prefersDark: false },
    { name: "stored cobalt, light", theme: "cobalt", mode: "light", prefersDark: true },
    { name: "unknown theme", theme: "corporate", mode: "light", prefersDark: false },
    { name: "nothing stored, OS dark", prefersDark: true },
    { name: "nothing stored, OS light", prefersDark: false },
    { name: "system mode, OS dark", theme: "pebble", mode: "system", prefersDark: true },
    { name: "garbage values", theme: 42, mode: "blue", prefersDark: true },
  ];

  it.each(cases)("boot script and React agree: $name", ({ theme, mode, prefersDark }) => {
    const storage: Record<string, string> = {};
    if (theme !== undefined) storage[localStorageKey(UI_THEME_STORAGE_KEY)] = JSON.stringify(theme);
    if (mode !== undefined) storage[localStorageKey(THEME_MODE_STORAGE_KEY)] = JSON.stringify(mode);
    const attributes = boot(storage, prefersDark);
    expect(attributes["data-ui-theme"]).toBe(resolveUiTheme(theme));
    const dark = computeDarkMode((mode ?? "system") as ThemeMode, prefersDark);
    expect(attributes["data-theme"]).toBe(dark ? "dark" : "light");
  });

  it("falls back to the default theme and the OS mode when storage is unavailable", () => {
    expect(boot("unavailable", true)).toEqual({ "data-ui-theme": "pebble", "data-theme": "dark" });
  });

  it("uses light when the browser has no matchMedia, as React does", () => {
    expect(boot({}, "unsupported")).toEqual({ "data-ui-theme": "pebble", "data-theme": "light" });
  });

  it("resolves an unknown stored theme to pebble", () => {
    expect(resolveUiTheme("corporate")).toBe("pebble");
    expect(boot({ [localStorageKey(UI_THEME_STORAGE_KEY)]: JSON.stringify("corporate") }, false)["data-ui-theme"]).toBe(
      "pebble",
    );
  });
});
