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

import { createContext, PropsWithChildren, useEffect, useRef, useState } from "react";
import { ApplicationContextStruct, ThemeMode } from "./ApplicationContextStruct.tsx";
import { getPlatformUiThemes } from "../common/config.tsx";
import {
  cachePlatformUiThemes,
  computeDarkMode,
  offeredUiThemes,
  resolveUiTheme,
  UiTheme,
  type PlatformUiThemes,
} from "./uiThemes.ts";
import {
  saveUserPreference,
  persistUserPreference,
  updateCurrentUserPreference,
  useCurrentUserPreference,
} from "./userPreferences";

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

export const ApplicationContextProvider = (props: PropsWithChildren<{}>) => {
  return <ApplicationThemeProvider platformUiThemes={getPlatformUiThemes()}>{props.children}</ApplicationThemeProvider>;
};

/** Shared presentation state; platform settings come from startup configuration. */
export const ApplicationThemeProvider = ({
  children,
  platformUiThemes,
}: PropsWithChildren<{ platformUiThemes: PlatformUiThemes | null }>) => {
  const isSidebarCollapsed = useCurrentUserPreference("sidebar_collapsed", false);
  // Default to "system" so the first load honours the OS preference (prefers-color-scheme);
  // an explicit Light/Dark/System choice is also saved in the user's profile.
  const themeMode = useCurrentUserPreference("theme_mode", "system") as ThemeMode;
  // null = no choice yet, so the platform default can apply (see resolveUiTheme).
  const storedUiTheme = useCurrentUserPreference("ui_theme_id", null);
  const confirmedMode = useRef(themeMode);
  const confirmedTheme = useRef(storedUiTheme);
  const modeChange = useRef(0);
  const themeChange = useRef(0);
  useEffect(() => cachePlatformUiThemes(platformUiThemes), [platformUiThemes]);
  const uiTheme = resolveUiTheme(storedUiTheme, platformUiThemes);
  const offered = offeredUiThemes(platformUiThemes);
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
    const next = !isSidebarCollapsed;
    persistUserPreference({ sidebar_collapsed: next });
  };

  const setThemeMode = (mode: ThemeMode, onError?: (error: unknown) => void) => {
    const change = ++modeChange.current;
    updateCurrentUserPreference({ theme_mode: mode });
    void saveUserPreference({ theme_mode: mode })
      .then(() => {
        confirmedMode.current = mode;
      })
      .catch((error) => {
        if (change === modeChange.current) {
          updateCurrentUserPreference({ theme_mode: confirmedMode.current });
          onError?.(error);
        }
      });
  };

  const setUiTheme = (theme: UiTheme, onError?: (error: unknown) => void) => {
    const change = ++themeChange.current;
    updateCurrentUserPreference({ ui_theme_id: theme });
    void saveUserPreference({ ui_theme_id: theme })
      .then(() => {
        confirmedTheme.current = theme;
      })
      .catch((error) => {
        if (change === themeChange.current) {
          updateCurrentUserPreference({ ui_theme_id: confirmedTheme.current });
          onError?.(error);
        }
      });
  };

  const contextValue: ApplicationContextStruct = {
    isSidebarCollapsed,
    darkMode,
    themeMode,
    uiTheme,
    offeredUiThemes: offered,
    toggleSidebar,
    setThemeMode,
    setUiTheme,
  };

  return <ApplicationContext.Provider value={contextValue}>{children}</ApplicationContext.Provider>;
};
