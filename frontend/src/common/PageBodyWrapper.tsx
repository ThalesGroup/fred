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
