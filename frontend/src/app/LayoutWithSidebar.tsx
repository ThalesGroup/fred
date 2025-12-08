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

import { Box, CssBaseline } from "@mui/material";
import { Outlet } from "react-router-dom";
import SideBar from "./SideBar";

export const LayoutWithSidebar = ({ children }: React.PropsWithChildren<{}>) => {
  return (
    <>
      <CssBaseline enableColorScheme />
      {/* 🔒 App frame owns the viewport; prevent body scrolling */}
      <Box
        sx={{
          display: "flex",
          height: "100vh", // viewport-locked container
          overflow: "hidden", // body never scrolls; only inner panes do
        }}
      >
        <SideBar />

        {/* 👉 Right pane is a flex column that hosts the routed pages */}
        <Box
          sx={{
            flex: 1,
            minWidth: 0, // prevents flex overflow with long content
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* 🌀 This is the ONLY vertical scroller in the app shell */}
          <Box sx={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
            {children}
            <Outlet />
          </Box>
        </Box>
      </Box>
    </>
  );
};
