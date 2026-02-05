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

import { alpha, Box, styled, SxProps, Tabs, Theme } from "@mui/material";
import * as React from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { LinkTab } from "./LinkTab";

const BubbleTab = styled(Tabs)(({ theme }) => ({
  "& .MuiTabs-flexContainer": {
    gap: "2px",
  },
  "& .MuiTabs-indicator": {
    display: "none", // Hide the default underline indicator

    // to have a moving indicator:
    // backgroundColor: alpha(theme.palette.primary.main, 0.16),
    // height: "100%",
    // borderRadius: theme.spacing(1.5),
    // transition: theme.transitions.create(["left", "width"], {
    //   duration: theme.transitions.duration.shorter,
    //   easing: theme.transitions.easing.easeInOut,
    // }),
  },
  "& .MuiTab-root": {
    minHeight: 40,
    textTransform: "none",
    fontWeight: theme.typography.fontWeightMedium,
    fontSize: theme.typography.pxToRem(14),
    padding: theme.spacing(0, 2),
    borderRadius: theme.spacing(1.5),
    transition: theme.transitions.create(["background-color", "color"], {
      duration: theme.transitions.duration.shortest,
    }),
    "&:hover": {
      backgroundColor: theme.palette.action.hover,
    },
    "&.Mui-selected": {
      color: theme.palette.text.primary,
      backgroundColor: alpha(theme.palette.primary.main, 0.16),
    },
    "& .MuiTouchRipple-root": {
      display: "none",
    },
  },
}));

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
   * Optional sx props for the tabs container Box
   */
  tabsContainerSx?: SxProps<Theme>;
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

export function NavigationTabs({ tabs, defaultPath, tabsContainerSx, contentContainerSx, isLoading }: NavigationTabsProps) {
  const location = useLocation();

  // Find the current tab index based on the pathname
  const currentTabIndex = tabs.findIndex((tab) => location.pathname === tab.path);
  const tabValue = currentTabIndex !== -1 ? currentTabIndex : false;

  // Extract relative paths from absolute paths for nested routing
  const getRelativePath = (absolutePath: string) => {
    const parts = absolutePath.split("/");
    return parts[parts.length - 1]; // Get the last segment (e.g., "drafts" from "/team/0/drafts")
  };

  // Use the provided default path (absolute) or the first tab's path
  const redirectToPath = defaultPath || tabs[0]?.path || "";

  return (
    <>
      <Box sx={tabsContainerSx}>
        <BubbleTab value={tabValue} aria-label="navigation tabs">
          {tabs.map((tab) => (
            <LinkTab key={tab.path} label={tab.label} to={tab.path} />
          ))}
        </BubbleTab>
      </Box>
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
    </>
  );
}
