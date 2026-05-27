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
 * Computes the effective dark mode based on theme mode and system preference
 */
const computeDarkMode = (themeMode: ThemeMode, systemDarkMode: boolean): boolean => {
  if (themeMode === "system") {
    return systemDarkMode;
  }
  return themeMode === "dark";
};

export const ApplicationContextProvider = (props: PropsWithChildren<{}>) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useLocalStorageState(
    "ApplicationContextProvider.isSidebarCollapsed",
    false,
  );
  const [themeMode, setThemeMode] = useLocalStorageState<ThemeMode>("ApplicationContextProvider.themeMode", "dark");
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
    toggleSidebar,
    setThemeMode,
  };

  return <ApplicationContext.Provider value={contextValue}>{props.children}</ApplicationContext.Provider>;
};
