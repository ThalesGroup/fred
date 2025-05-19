import { Outlet } from "react-router-dom";
import { useContext } from "react";
import { ApplicationContext } from "./ApplicationContextProvider";
import SideBar from "./SideBar";
import { Box, CssBaseline } from "@mui/material";

export const LayoutWithSidebar = () => {
  const { darkMode, toggleDarkMode } = useContext(ApplicationContext);

  return (
    <>
      <CssBaseline />
      <Box sx={{ display: "flex" }}>
        <SideBar darkMode={darkMode} onThemeChange={toggleDarkMode} />
        <Box sx={{ flexGrow: 1 }}>
          <Outlet />
        </Box>
      </Box>
    </>
  );
};
