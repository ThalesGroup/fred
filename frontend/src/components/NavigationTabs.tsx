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

import * as React from "react";
import { Box, Tabs } from "@mui/material";
import { useLocation, Routes, Route, Navigate } from "react-router-dom";
import { LinkTab } from "./LinkTab";

export interface TabConfig {
  label: string;
  path: string;
  component: React.ReactNode;
}

interface NavigationTabsProps {
  tabs: TabConfig[];
  /**
   * Optional base path to redirect to when no tab matches.
   * Defaults to the first tab's path.
   */
  defaultPath?: string;
}

export function NavigationTabs({ tabs, defaultPath }: NavigationTabsProps) {
  const location = useLocation();

  // Find the current tab index based on the pathname
  const currentTabIndex = tabs.findIndex((tab) => location.pathname === tab.path);
  const tabValue = currentTabIndex !== -1 ? currentTabIndex : false;

  // Extract relative paths from absolute paths for nested routing
  const getRelativePath = (absolutePath: string) => {
    const parts = absolutePath.split('/');
    return parts[parts.length - 1]; // Get the last segment (e.g., "drafts" from "/team/0/drafts")
  };

  // Use the provided default path (absolute) or the first tab's path
  const redirectToPath = defaultPath || tabs[0]?.path || '';

  return (
    <Box>
      <Tabs value={tabValue} aria-label="navigation tabs">
        {tabs.map((tab) => (
          <LinkTab key={tab.path} label={tab.label} to={tab.path} />
        ))}
      </Tabs>
      <Box sx={{ mt: 2 }}>
        <Routes>
          {tabs.map((tab) => {
            const relativePath = getRelativePath(tab.path);
            return (
              <Route key={relativePath} path={relativePath} element={<>{tab.component}</>} />
            );
          })}
          <Route index element={<Navigate to={redirectToPath} replace />} />
          <Route path="*" element={<Navigate to={redirectToPath} replace />} />
        </Routes>
      </Box>
    </Box>
  );
}
