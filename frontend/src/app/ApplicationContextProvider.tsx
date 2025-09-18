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
import { ApplicationContextStruct } from "./ApplicationContextStruct.tsx";

/**
 * Our application context.
 */
export const ApplicationContext = createContext<ApplicationContextStruct>(null!);
export const ApplicationContextProvider = (props: PropsWithChildren<{}>) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(true);
  // Load user preferences from local storage on app startup
  useEffect(() => {
    const storedSidebarState = localStorage.getItem("isSidebarCollapsed");
    const storedThemeMode = localStorage.getItem("darkMode");

    if (storedSidebarState !== null) {
      setIsSidebarCollapsed(JSON.parse(storedSidebarState));
    }
    if (storedThemeMode !== null) {
      setDarkMode(JSON.parse(storedThemeMode));
    }
  }, []);

  // Save sidebar state to local storage when it changes
  useEffect(() => {
    localStorage.setItem("isSidebarCollapsed", JSON.stringify(isSidebarCollapsed));
  }, [isSidebarCollapsed]);

  // Save dark mode preference to local storage when it changes
  useEffect(() => {
    localStorage.setItem("darkMode", JSON.stringify(darkMode));
  }, [darkMode]);

  const toggleSidebar = () => {
    setIsSidebarCollapsed((prevState) => !prevState);
  };

  const toggleDarkMode = () => {
    setDarkMode((prevState) => !prevState);
  };

  const contextValue: ApplicationContextStruct = {
    isSidebarCollapsed,
    darkMode,
    toggleSidebar,
    toggleDarkMode,
  };

  return <ApplicationContext.Provider value={contextValue}>{props.children}</ApplicationContext.Provider>;
};