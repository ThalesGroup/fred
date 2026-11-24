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

import {
  createContext,
  PropsWithChildren,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useSyncExternalStore,
} from "react";
import { ApplicationContextStruct, ThemeMode } from "./ApplicationContextStruct.tsx";
import { getPlatformUiThemes } from "../common/config.tsx";
import { useFrontendConfigQuery } from "../slices/controlPlane/controlPlaneApiEnhancements";
import {
  saveUserPreference,
  persistUserPreference,
  updateCurrentUserPreference,
  useCurrentUserPreference,
} from "./userPreferences";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "../rework/core/hooks/crossSessionRefresh";
import { useMediaQuery } from "../rework/core/hooks/useMediaQuery";
import {
  cachePlatformUiThemes,
  computeDarkMode,
  getThemeDaylight,
  LocalDaylight,
  offeredUiThemes,
  resolveUiTheme,
  UiTheme,
} from "./uiThemes.ts";

/**
 * Our application context.
 */
export const ApplicationContext = createContext<ApplicationContextStruct>(null!);

function useLocalDaylight(schedule?: LocalDaylight) {
  const clock = window.fredLocalDaylight;
  useLayoutEffect(() => {
    clock?.paint(schedule ? clock.sample(schedule, new Date()) : null);
  }, [clock, schedule]);

  const subscribe = useCallback(
    (notify: () => void) => {
      if (!schedule || !clock) return () => {};
      let timer: number;
      const refresh = () => {
        window.clearTimeout(timer);
        if (document.hidden) return;
        const now = new Date();
        clock.paint(clock.sample(schedule, now));
        notify();
        timer = window.setTimeout(refresh, 60_000 - (now.getTime() % 60_000));
      };
      refresh();
      document.addEventListener("visibilitychange", refresh);
      window.addEventListener("pageshow", refresh);
      return () => {
        window.clearTimeout(timer);
        document.removeEventListener("visibilitychange", refresh);
        window.removeEventListener("pageshow", refresh);
      };
    },
    [clock, schedule],
  );
  return useSyncExternalStore(subscribe, () => schedule && clock?.sample(schedule, new Date()).dark);
}

export const ApplicationContextProvider = (props: PropsWithChildren<{}>) => {
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
  const { data: publicConfig, refetch } = useFrontendConfigQuery(undefined, crossSessionRefreshOptions(false));
  useRefetchOnWindowFocus(refetch, false);
  const platformUiThemes = publicConfig ? (publicConfig.ui_themes ?? null) : getPlatformUiThemes();
  useEffect(() => cachePlatformUiThemes(platformUiThemes), [platformUiThemes]);
  const uiTheme = resolveUiTheme(storedUiTheme, platformUiThemes);
  const offered = offeredUiThemes(platformUiThemes);
  const systemDarkMode = useMediaQuery("(prefers-color-scheme: dark)");
  const clockDark = useLocalDaylight(themeMode === "system" ? getThemeDaylight(uiTheme) : undefined);
  const darkMode = clockDark ?? computeDarkMode(themeMode, systemDarkMode);

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

  return <ApplicationContext.Provider value={contextValue}>{props.children}</ApplicationContext.Provider>;
};
