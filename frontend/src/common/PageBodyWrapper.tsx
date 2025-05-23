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

import { Box, useTheme } from "@mui/material";
import { useContext } from "react";
import { ApplicationContext } from "../app/ApplicationContextProvider";

export const PageBodyWrapper = ({ children }: { children: React.ReactNode }) => {
  const { isSidebarCollapsed } = useContext(ApplicationContext);
  const theme = useTheme();
  const sidebarWidth = isSidebarCollapsed
  ? theme.layout.sidebarCollapsedWidth
  : theme.layout.sidebarWidth;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "row",
      }}
    >
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          marginLeft: `${sidebarWidth}px`,
          width: `calc(100% - ${sidebarWidth}px)`,
          backgroundColor: "background.default",
          minHeight: "100vh",
          overflowX: "hidden",
          overflowY: "auto",
          transition: (theme) =>
            theme.transitions.create(["margin", "width"], {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.standard,
            }),
        }}
      >
        {children}
      </Box>
    </Box>
  );
};
