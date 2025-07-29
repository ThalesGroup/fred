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

import { Outlet } from "react-router-dom";
import { useContext } from "react";
import { ApplicationContext } from "./ApplicationContextProvider";
import SideBar from "./SideBar";
import { Box, CssBaseline } from "@mui/material";

export const LayoutWithSidebar = ({ children }: React.PropsWithChildren<{}>) => {
  const { darkMode, toggleDarkMode } = useContext(ApplicationContext);

  return (
    <>
      <CssBaseline enableColorScheme />
      <Box sx={{ display: "flex" }}>
        <SideBar darkMode={darkMode} onThemeChange={toggleDarkMode} />
        <Box
          sx={{
            flexGrow: 1,
            height: "100vh",
            overflow: "auto",
          }}
        >
          {children}
          <Outlet />
        </Box>
      </Box>
    </>
  );
};
