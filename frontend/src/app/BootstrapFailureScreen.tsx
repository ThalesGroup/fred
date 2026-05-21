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

import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import { Box, Button, CssBaseline, ThemeProvider, useMediaQuery } from "@mui/material";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ConfigLoadFailureDetails } from "../common/config";
import { EmptyState } from "../components/EmptyState";
import { createDarkTheme, createLightTheme } from "../styles/theme";

type BootstrapFailureScreenProps = {
  failure: ConfigLoadFailureDetails;
  onRetry: () => void;
};

/**
 * Shows one full-page startup fallback when the UI cannot even finish loading its config.
 *
 * Why: without this screen, a bootstrap-time 502/503 leaves the browser on a white page
 * because the router and normal in-app error handling are not mounted yet.
 *
 * How: render it directly from `index.tsx` when `loadConfig()` fails before the app starts.
 * The component mirrors the application's light/dark look from `prefers-color-scheme`
 * because the normal app-level theme providers do not exist yet at bootstrap time.
 */
export function BootstrapFailureScreen({ failure, onRetry }: BootstrapFailureScreenProps) {
  const { t } = useTranslation();
  const prefersDarkMode = useMediaQuery("(prefers-color-scheme: dark)", { noSsr: true });
  const isBackendUnavailable = failure.kind === "backend_unavailable";
  const homeUrl = import.meta.env.BASE_URL ?? "/";
  const theme = useMemo(() => {
    document.documentElement.setAttribute("data-theme", prefersDarkMode ? "dark" : "light");
    return prefersDarkMode ? createDarkTheme() : createLightTheme();
  }, [prefersDarkMode]);
  const title = isBackendUnavailable
    ? t("bootstrapFailure.backendUnavailableTitle", "Service temporarily unavailable")
    : t("bootstrapFailure.genericTitle", "Application could not start");
  const description = isBackendUnavailable
    ? t(
        "bootstrapFailure.backendUnavailableDescription",
        "The application is temporarily refusing new connections. Please retry in a few moments.",
      )
    : t(
        "bootstrapFailure.genericDescription",
        "The application configuration could not be loaded. Please retry, or contact support if the issue persists.",
      );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline enableColorScheme />
      <Box
        sx={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          px: 3,
          width: "100vw",
        }}
      >
        <Box sx={{ width: "100%", maxWidth: 720 }}>
          <EmptyState
            icon={
              <ErrorOutlineRoundedIcon
                sx={{
                  color: isBackendUnavailable ? "warning.main" : "error.main",
                }}
              />
            }
            title={title}
            description={description}
            descriptionMaxWidth={"60ch"}
            actionButton={{
              label: t("bootstrapFailure.retry", "Retry"),
              onClick: onRetry,
              startIcon: <RefreshRoundedIcon />,
              variant: "outlined",
            }}
          />
          <Box sx={{ display: "flex", justifyContent: "center", mt: 1 }}>
            <Button variant="text" size="small" onClick={() => window.location.assign(homeUrl)}>
              {t("bootstrapFailure.home", "Open home")}
            </Button>
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}
