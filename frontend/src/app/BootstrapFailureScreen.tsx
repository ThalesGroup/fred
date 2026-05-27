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
import { Box, CssBaseline } from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";
import { useContext, useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ConfigLoadFailureDetails } from "../common/config";
import { EmptyState } from "../components/EmptyState";
import { createDarkTheme, createLightTheme } from "../styles/theme";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";

type BootstrapFailureScreenProps = {
  failure: ConfigLoadFailureDetails;
  onRetry: () => void;
};

/**
 * Renders the fallback content with the same theme selection rules as the app shell.
 *
 * Why: the bootstrap error screen is mounted before the normal application tree,
 * but it still needs the shared light/dark resolution from `ApplicationContextProvider`.
 *
 * How: mount this only inside `ApplicationContextProvider`, then it can derive
 * `darkMode` from the shared context before creating the MUI theme.
 */
function BootstrapFailureScreenContent({ failure, onRetry }: BootstrapFailureScreenProps) {
  const { t } = useTranslation();
  const { darkMode } = useContext(ApplicationContext);
  const isBackendUnavailable = failure.kind === "backend_unavailable";
  const theme = useMemo(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
    return darkMode ? createDarkTheme() : createLightTheme();
  }, [darkMode]);
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
          backgroundColor: "background.default",
          color: "text.primary",
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
              variant: "contained",
            }}
          />
        </Box>
      </Box>
    </ThemeProvider>
  );
}

/**
 * Shows one full-page startup fallback when the UI cannot even finish loading its config.
 *
 * Why: without this screen, a bootstrap-time 502/503 leaves the browser on a white page
 * because the router and normal in-app error handling are not mounted yet.
 *
 * How: render it directly from `index.tsx` when `loadConfig()` fails before the app starts.
 */
export function BootstrapFailureScreen({ failure, onRetry }: BootstrapFailureScreenProps) {
  return (
    <ApplicationContextProvider>
      <BootstrapFailureScreenContent failure={failure} onRetry={onRetry} />
    </ApplicationContextProvider>
  );
}
