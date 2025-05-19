// FredUi.tsx
import React, { useState, useEffect, useContext } from "react";
import { RouterProvider } from "react-router-dom";
import { ToastProvider } from "../components/ToastProvider";
import { ConfirmationDialogProvider } from "../components/ConfirmationDialogProvider";
import { ApplicationContextProvider, ApplicationContext } from "./ApplicationContextProvider";
import { ThemeProvider } from "@mui/material/styles";
import { lightTheme, darkTheme } from "../styles/theme";

function FredUi() {
  const [router, setRouter] = useState<any>(null);

  useEffect(() => {
    // Dynamically import the router after config has loaded
    import("./router").then((mod) => {
      setRouter(mod.router);
    });
  }, []);

  if (!router) return <div>Loading app...</div>;

  return (
    <React.Suspense fallback={<div>Loading UI...</div>}>
      <ToastProvider>
        <ConfirmationDialogProvider>
          <ApplicationContextProvider>
            <AppWithTheme router={router} />
          </ApplicationContextProvider>
        </ConfirmationDialogProvider>
      </ToastProvider>
    </React.Suspense>
  );
}

function AppWithTheme({ router }: { router: any }) {
  const { darkMode } = useContext(ApplicationContext);
  const theme = darkMode ? darkTheme : lightTheme;

  return (
    <ThemeProvider theme={theme}>
      <RouterProvider router={router} />
    </ThemeProvider>
  );
}

export default FredUi;
