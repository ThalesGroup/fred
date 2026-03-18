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

import { Box, SxProps, Theme } from "@mui/material";
import * as React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

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
  /**
   * Optional sx props for the content container Box
   */
  contentContainerSx?: SxProps<Theme>;
  /**
   * When true, prevents redirecting to defaultPath if current path doesn't match any tab.
   * Useful when tabs are dynamically loaded based on async data (e.g., permissions).
   */
  isLoading?: boolean;
}

export function NavigationTabs({
  tabs,
  defaultPath,
  contentContainerSx,
  isLoading,
}: NavigationTabsProps) {
  // Extract relative paths from absolute paths for nested routing
  const getRelativePath = (absolutePath: string) => {
    const parts = absolutePath.split("/");
    return parts[parts.length - 1]; // Get the last segment (e.g., "drafts" from "/team/0/drafts")
  };

  // Use the provided default path (absolute) or the first tab's path
  const redirectToPath = defaultPath || tabs[0]?.path || "";

  return (
    <Box sx={contentContainerSx}>
      <Routes>
        {tabs.map((tab) => {
          const relativePath = getRelativePath(tab.path);
          return <Route key={relativePath} path={relativePath} element={<>{tab.component}</>} />;
        })}
        <Route index element={<Navigate to={redirectToPath} replace />} />
        {!isLoading && <Route path="*" element={<Navigate to={redirectToPath} replace />} />}
      </Routes>
    </Box>
  );
}
