// Copyright Thales 2025
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

import { createContext, PropsWithChildren, useEffect, useState } from "react";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { ApplicationContextStruct, ThemeMode } from "./ApplicationContextStruct.tsx";
import { DEFAULT_UI_THEME, resolveUiTheme, THEME_MODE_STORAGE_KEY, UI_THEME_STORAGE_KEY, UiTheme } from "./uiThemes.ts";

/**
 * Our application context.
 */
export const ApplicationContext = createContext<ApplicationContextStruct>(null!);

/**
 * Detects if the user's system prefers dark mode
 */
const getSystemDarkMode = (): boolean => {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
};

/**
 * Computes the effective dark mode: an explicit light/dark choice wins, anything
 * else (system, absent, unknown) follows the OS, as public/theme-boot.js does.
 */
export const computeDarkMode = (themeMode: ThemeMode, systemDarkMode: boolean): boolean => {
  if (themeMode === "dark") return true;
  if (themeMode === "light") return false;
  return systemDarkMode;
};

export const ApplicationContextProvider = (props: PropsWithChildren<{}>) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useLocalStorageState(
    "ApplicationContextProvider.isSidebarCollapsed",
    false,
  );
  // Default to "system" so the first load honours the OS preference (prefers-color-scheme);
  // an explicit Light/Dark/System choice from the settings toggle then persists in localStorage.
  const [themeMode, setThemeMode] = useLocalStorageState<ThemeMode>(THEME_MODE_STORAGE_KEY, "system");
  const [storedUiTheme, setUiTheme] = useLocalStorageState<UiTheme>(UI_THEME_STORAGE_KEY, DEFAULT_UI_THEME);
  const uiTheme = resolveUiTheme(storedUiTheme);
  const [systemDarkMode, setSystemDarkMode] = useState(getSystemDarkMode());
  const darkMode = computeDarkMode(themeMode, systemDarkMode);

  // Listen for system theme changes
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (e: MediaQueryListEvent) => {
      setSystemDarkMode(e.matches);
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  const toggleSidebar = () => {
    setIsSidebarCollapsed((prevState) => !prevState);
  };

  const contextValue: ApplicationContextStruct = {
    isSidebarCollapsed,
    darkMode,
    themeMode,
    uiTheme,
    toggleSidebar,
    setThemeMode,
    setUiTheme,
  };

  return <ApplicationContext.Provider value={contextValue}>{props.children}</ApplicationContext.Provider>;
};
