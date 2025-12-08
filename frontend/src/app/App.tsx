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
import { Box, CircularProgress, Typography } from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";
import React, { useContext, useEffect, useMemo, useState } from "react";
import { RouterProvider } from "react-router-dom";
import { ConfirmationDialogProvider } from "../components/ConfirmationDialogProvider";
import { DrawerProvider } from "../components/DrawerProvider";
import { ToastProvider } from "../components/ToastProvider";
import { darkTheme, lightTheme } from "../styles/theme";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import { AuthProvider } from "../security/AuthContext";
import { useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery } from "../slices/agentic/agenticOpenApi";
import { useTranslation } from "react-i18next";

const LoadingScreen = ({ label, dark }: { label: string; dark: boolean }) => {
  const bg = dark
    ? "radial-gradient(circle at 20% 20%, rgba(0,108,255,0.08), transparent 35%), radial-gradient(circle at 80% 30%, rgba(0,220,200,0.10), transparent 30%), linear-gradient(135deg, #0b1f3a, #0e274a 35%, #0b1f3a)"
    : "radial-gradient(circle at 20% 20%, rgba(0,90,255,0.06), transparent 35%), radial-gradient(circle at 80% 30%, rgba(0,180,200,0.12), transparent 30%), linear-gradient(135deg, #f5f8ff, #e8f0ff 35%, #f5f8ff)";

  const accent = dark ? "#7dd8ff" : "#1e5eff";
  const panelBg = dark ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.85)";
  const textColor = dark ? "#e6edff" : "#0d2145";

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: bg,
        color: textColor,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(circle at 50% 110%, rgba(255,255,255,0.06), transparent 35%)",
          pointerEvents: "none",
        }}
      />
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          px: 3,
          py: 2,
          borderRadius: 2,
          backdropFilter: "blur(8px)",
          backgroundColor: panelBg,
          boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
          zIndex: 1,
        }}
      >
        <CircularProgress size={42} thickness={4} sx={{ color: accent }} />
        <Typography variant="subtitle1" sx={{ letterSpacing: 0.5, fontWeight: 600 }}>
          {label}
        </Typography>
      </Box>
    </Box>
  );
};

function FredUi() {
  const [router, setRouter] = useState<any>(null);
  const { data: frontendConfig } = useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery();
  const { t } = useTranslation();
  const siteDisplayName = frontendConfig?.frontend_settings?.properties?.siteDisplayName || "Fred";
  const logoName = frontendConfig?.frontend_settings?.properties?.logoName || "fred";
  const logoNameDark = frontendConfig?.frontend_settings?.properties?.logoNameDark || "fred-dark";
  const [prefersDark, setPrefersDark] = useState<boolean>(() => {
    const stored = localStorage.getItem("darkMode");
    if (stored !== null) return stored === "true";
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? false;
  });

  useEffect(() => {
    document.title = siteDisplayName;
    const favicon = document.getElementById("favicon") as HTMLLinkElement;
    const isDark = window.matchMedia("(prefers-color-scheme: dark)");
    if (isDark.matches) favicon.href = `/images/${logoNameDark}.svg`;
    else favicon.href = `/images/${logoName}.svg`;

    const listener = (event: MediaQueryListEvent) => setPrefersDark(event.matches);
    const storageListener = (event: StorageEvent) => {
      if (event.key === "darkMode" && event.newValue !== null) {
        setPrefersDark(event.newValue === "true");
      }
    };
    isDark.addEventListener("change", listener);
    window.addEventListener("storage", storageListener);
    return () => {
      isDark.removeEventListener("change", listener);
      window.removeEventListener("storage", storageListener);
    };
  }, [siteDisplayName, logoName]);

  useEffect(() => {
    import("../common/router").then((mod) => {
      setRouter(mod.router);
    });
  }, []);

  if (!router) return <LoadingScreen label={t("app.loading.router", "Fred démarre...")} dark={prefersDark} />;

  return (
    <React.Suspense fallback={<LoadingScreen label={t("app.loading.ui", "L'interface Fred se prépare...")} dark={prefersDark} />}>
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
