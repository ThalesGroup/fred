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
import { Box, Typography } from "@mui/material";
import { ThemeProvider, keyframes } from "@mui/material/styles";
import React, { useContext, useEffect, useState } from "react";
import { RouterProvider } from "react-router-dom";
import { ConfirmationDialogProvider } from "../components/ConfirmationDialogProvider";
import { DrawerProvider } from "../components/DrawerProvider";
import { ToastProvider } from "../components/ToastProvider";
import { darkTheme, lightTheme } from "../styles/theme";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import { AuthProvider } from "../security/AuthContext";
import { useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery } from "../slices/agentic/agenticOpenApi";
import { useTranslation } from "react-i18next";

const pulse = keyframes`
  0% { transform: scale(1); opacity: 0.9; }
  50% { transform: scale(1.08); opacity: 1; }
  100% { transform: scale(1); opacity: 0.9; }
`;

const LoadingScreen = ({
  label,
  dark,
  logoName,
  logoNameDark,
  alt,
}: {
  label: string;
  dark: boolean;
  logoName: string;
  logoNameDark: string;
  alt: string;
}) => {
  const palette = dark ? darkTheme.palette : lightTheme.palette;
  const bg = dark ? palette.background.default : palette.surfaces.soft;
  const textColor = palette.text.primary;

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
          px: 2.5,
          py: 2,
          borderRadius: 3,
          backdropFilter: "none",
          backgroundColor: "transparent",
          boxShadow: "none",
          zIndex: 1,
          width: 170,
          justifyContent: "center",
        }}
      >
        <Box
          component="img"
          src={`/images/${dark ? logoNameDark : logoName}.svg`}
          alt={alt}
          sx={{
            width: 68,
            height: 68,
            animation: `${pulse} 1.8s ease-in-out infinite`,
            filter: dark
              ? "drop-shadow(0 6px 16px rgba(0,0,0,0.35))"
              : "drop-shadow(0 6px 16px rgba(0,0,0,0.12))",
          }}
        />
        <Typography
          component="span"
          sx={{
            position: "absolute",
            width: 1,
            height: 1,
            padding: 0,
            margin: -1,
            overflow: "hidden",
            clip: "rect(0,0,0,0)",
            whiteSpace: "nowrap",
            border: 0,
          }}
        >
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

  if (!router)
    return (
      <LoadingScreen
        label={t("app.loading.router", "Fred démarre...")}
        dark={prefersDark}
        logoName={logoName}
        logoNameDark={logoNameDark}
        alt={siteDisplayName}
      />
    );

  return (
    <React.Suspense
      fallback={
        <LoadingScreen
          label={t("app.loading.ui", "L'interface Fred se prépare...")}
          dark={prefersDark}
          logoName={logoName}
          logoNameDark={logoNameDark}
          alt={siteDisplayName}
        />
      }
    >
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
