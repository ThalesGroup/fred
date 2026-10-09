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

import { localStorageKey } from "../hooks/useLocalStorageState.ts";
import type { FrontendUiThemes } from "../slices/controlPlane/controlPlaneOpenApi";

/**
 * UI theme catalog (palette, font, radii; each has a light and a dark mode).
 * public/theme-boot.js applies the same rules before the first paint and keeps
 * its own copy of this list; uiThemes.test.ts checks they match.
 */
export const UI_THEMES = ["pebble", "cobalt", "cloud"] as const;
export type UiTheme = string;
export type CustomUiTheme = { id: string; label: string; base: (typeof UI_THEMES)[number] };
let customThemes: CustomUiTheme[] = [];

/** i18n key of each theme's display name (profile picker, admin page). */
export const UI_THEME_LABEL_KEYS: Record<string, string> = {
  pebble: "rework.userSettings.app.themePebble",
  cobalt: "rework.userSettings.app.themeCobalt",
  cloud: "rework.userSettings.app.themeCloud",
};

/** Hook keys; useLocalStorageState stores them under localStorageKey(key). */
export const UI_THEME_STORAGE_KEY = "ApplicationContextProvider.uiTheme";
export const THEME_MODE_STORAGE_KEY = "ApplicationContextProvider.themeMode";

/** Platform settings from the public /frontend/config (ids may be unknown here). */
export type PlatformUiThemes = FrontendUiThemes;

/** Last platform settings seen, read by theme-boot.js before the next load's config arrives. */
export const PLATFORM_UI_THEMES_CACHE_KEY = localStorageKey("ApplicationContextProvider.platformUiThemes");
export const CUSTOM_UI_THEMES_CACHE_KEY = localStorageKey("ApplicationContextProvider.customUiThemes");

export function setCustomUiThemes(themes: CustomUiTheme[]): void {
  customThemes = themes;
  try {
    window.localStorage.setItem(CUSTOM_UI_THEMES_CACHE_KEY, JSON.stringify(themes));
  } catch {
    // Storage is optional; the fresh catalog still applies to this page load.
  }
}

export const availableUiThemes = (): UiTheme[] => [...UI_THEMES, ...customThemes.map((theme) => theme.id)];
export const uiThemeBase = (id: UiTheme): string => customThemes.find((theme) => theme.id === id)?.base ?? id;
export const uiThemeLabel = (id: UiTheme, t: (key: string) => string): string =>
  customThemes.find((theme) => theme.id === id)?.label ?? t(UI_THEME_LABEL_KEYS[id] ?? id);

const isUiTheme = (value: unknown): value is UiTheme =>
  typeof value === "string" && availableUiThemes().includes(value);

/** Shipped and not hidden; the hidden list is ignored if it would leave nothing. */
export function offeredUiThemes(platform?: PlatformUiThemes | null): UiTheme[] {
  const hidden = Array.isArray(platform?.hidden_themes) ? platform.hidden_themes : [];
  const offered = availableUiThemes().filter((theme) => !hidden.includes(theme));
  return offered.length > 0 ? offered : availableUiThemes();
}

/** User's choice if offered, else the platform default if offered, else the first offered theme. */
export function resolveUiTheme(stored: unknown, platform?: PlatformUiThemes | null): UiTheme {
  const offered = offeredUiThemes(platform);
  if (isUiTheme(stored) && offered.includes(stored)) return stored;
  const platformDefault = platform?.default_theme;
  if (isUiTheme(platformDefault) && offered.includes(platformDefault)) return platformDefault;
  return offered[0];
}

/** An explicit light/dark choice wins; anything else (system, absent, unknown) follows the OS. */
export const computeDarkMode = (themeMode: unknown, systemDarkMode: boolean): boolean => {
  if (themeMode === "dark") return true;
  if (themeMode === "light") return false;
  return systemDarkMode;
};

function readStored(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

/** Remembers the platform settings for theme-boot.js on the next load. */
export function cachePlatformUiThemes(platform: PlatformUiThemes | null): void {
  try {
    if (platform) window.localStorage.setItem(PLATFORM_UI_THEMES_CACHE_KEY, JSON.stringify(platform));
    else window.localStorage.removeItem(PLATFORM_UI_THEMES_CACHE_KEY);
  } catch {
    // Storage unavailable: theme-boot.js then falls back to the catalog default.
  }
}

/** Applies the resolved theme and mode to <html>; called once the fresh platform settings are known. */
export function applyResolvedTheme(platform: PlatformUiThemes | null): void {
  const theme = resolveUiTheme(readStored(localStorageKey(UI_THEME_STORAGE_KEY)), platform);
  const systemDark = !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const dark = computeDarkMode(readStored(localStorageKey(THEME_MODE_STORAGE_KEY)), systemDark);
  document.documentElement.setAttribute("data-ui-theme", theme);
  document.documentElement.setAttribute("data-ui-base-theme", uiThemeBase(theme));
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}
