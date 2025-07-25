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

// FredUi.tsx
import { ThemeProvider } from "@mui/material/styles";
import React, { useContext, useEffect, useState } from "react";
import { RouterProvider } from "react-router-dom";
import { ConfirmationDialogProvider } from "../components/ConfirmationDialogProvider";
import { DrawerProvider } from "../components/DrawerProvider";
import { ToastProvider } from "../components/ToastProvider";
import { darkTheme, lightTheme } from "../styles/theme";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";

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
      <ApplicationContextProvider>
        <AppWithTheme router={router} />
      </ApplicationContextProvider>
    </React.Suspense>
  );
}

function AppWithTheme({ router }: { router: any }) {
  const { darkMode } = useContext(ApplicationContext);
  const theme = darkMode ? darkTheme : lightTheme;

  return (
    <ThemeProvider theme={theme}>
      {/* Following providers (dialog, toast, drawer...) needs to be inside the ThemeProvider */}
      <ConfirmationDialogProvider>
        <ToastProvider>
          <DrawerProvider>
            <RouterProvider router={router} />
          </DrawerProvider>
        </ToastProvider>
      </ConfirmationDialogProvider>
    </ThemeProvider>
  );
}

export default FredUi;
