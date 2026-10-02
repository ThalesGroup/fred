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

/**
 * UI theme catalog (palette, font, radii; each has a light and a dark mode).
 * public/theme-boot.js applies the same rules before the first paint and keeps
 * its own copy of this list; uiThemes.test.ts checks they match.
 */
export const UI_THEMES = ["pebble", "cobalt", "cloud"] as const;
export type UiTheme = (typeof UI_THEMES)[number];
export const DEFAULT_UI_THEME: UiTheme = "pebble";

/** Hook keys; useLocalStorageState stores them under localStorageKey(key). */
export const UI_THEME_STORAGE_KEY = "ApplicationContextProvider.uiTheme";
export const THEME_MODE_STORAGE_KEY = "ApplicationContextProvider.themeMode";

/** A stored id the catalog no longer ships resolves to the default theme. */
export function resolveUiTheme(stored: unknown): UiTheme {
  return (UI_THEMES as readonly unknown[]).includes(stored) ? (stored as UiTheme) : DEFAULT_UI_THEME;
}
