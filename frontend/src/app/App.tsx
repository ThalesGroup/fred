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
import { AuthProvider } from "../security/AuthContext";
import { useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery } from "../slices/agentic/agenticOpenApi";

function FredUi() {
  const [router, setRouter] = useState<any>(null);
  const { data: frontendConfig } = useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery();
  const siteDisplayName = frontendConfig?.frontend_settings?.properties?.siteDisplayName || "Fred";
  const logoName = frontendConfig?.frontend_settings?.properties?.logoName || "fred";

  useEffect(() => {
    document.title = siteDisplayName;
    const favicon = document.getElementById("favicon") as HTMLLinkElement | null;
    if (favicon) {
      favicon.href = `/images/${logoName}.svg`;
    }
  }, [siteDisplayName, logoName]);

  useEffect(() => {
    import("../common/router").then((mod) => {
      setRouter(mod.router);
    });
  }, []);

  if (!router) return <div>Loading app...</div>;

  return (
    <React.Suspense fallback={<div>Loading UI...</div>}>
      <AuthProvider>
        <ApplicationContextProvider>
          <AppWithTheme router={router} />
        </ApplicationContextProvider>
      </AuthProvider>
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
