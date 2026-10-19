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
import { writeRichClipboard } from "@rework/utils/clipboardUtils";

import React, { useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RouterProvider } from "react-router-dom";
import { ConfirmationDialogProvider } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { ToastProvider } from "@shared/molecules/Toast/ToastProvider";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { AuthProvider } from "../security/AuthContext";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import { uiThemeBase, uiThemeTab } from "./uiThemes";
import styles from "./App.module.css";

const LoadingScreen = ({
  label,
  logoName,
  logoNameDark,
  alt,
}: {
  label: string;
  logoName: string;
  logoNameDark: string;
  alt: string;
}) => {
  const { darkMode } = useContext(ApplicationContext);
  const baseUrl = (import.meta.env.BASE_URL ?? "/").endsWith("/")
    ? (import.meta.env.BASE_URL ?? "/")
    : `${import.meta.env.BASE_URL ?? "/"}/`;

  return (
    <div className={styles.loadingScreen}>
      <div className={styles.logoBadge}>
        <img className={styles.logo} src={`${baseUrl}images/${darkMode ? logoNameDark : logoName}.svg`} alt={alt} />
        <span className={styles.srOnly}>{label}</span>
      </div>
    </div>
  );
};

function FredUiContent() {
  const [router, setRouter] = useState<any>(null);
  const { siteDisplayName, faviconName, logoName, faviconNameDark, logoNameDark } = useFrontendProperties();
  const { t } = useTranslation();
  const { darkMode, uiTheme } = useContext(ApplicationContext);
  const favicon = faviconName || logoName || "fred";
  const faviconDark = faviconNameDark || logoNameDark || "fred-dark";
  const baseUrl = (import.meta.env.BASE_URL ?? "/").endsWith("/")
    ? (import.meta.env.BASE_URL ?? "/")
    : `${import.meta.env.BASE_URL ?? "/"}/`;

  useEffect(() => {
    // Browser tab name follows the active ZIP theme, else the app display name.
    const tab = uiThemeTab(uiTheme, darkMode, siteDisplayName, favicon, faviconDark);
    document.title = tab.title;
    const faviconElement = document.getElementById("favicon") as HTMLLinkElement;
    faviconElement.href = `${baseUrl}images/${tab.icon}.svg`;
  }, [baseUrl, siteDisplayName, favicon, faviconDark, darkMode, uiTheme]);

  useEffect(() => {
    import("../common/router").then((mod) => {
      setRouter(mod.router);
    });
  }, []);

  if (!router)
    return (
      <LoadingScreen
        label={t("app.loading.router")}
        logoName={favicon}
        logoNameDark={faviconDark}
        alt={siteDisplayName}
      />
    );

  return (
    <React.Suspense
      fallback={
        <LoadingScreen
          label={t("app.loading.ui")}
          logoName={favicon}
          logoNameDark={faviconDark}
          alt={siteDisplayName}
        />
      }
    >
      <AuthProvider>
        <div className={styles.appShell}>
          <div className={styles.appContent}>
            <ConfirmationDialogProvider>
              <ToastProvider
                onCopy={async (text) => {
                  await writeRichClipboard("", text);
                }}
              >
                <RouterProvider router={router} />
              </ToastProvider>
            </ConfirmationDialogProvider>
          </div>
        </div>
      </AuthProvider>
    </React.Suspense>
  );
}

function AppWithTheme() {
  const { darkMode, uiTheme } = useContext(ApplicationContext);
  const { i18n } = useTranslation();

  // Effects run after render, which is too late for the first paint to pick
  // up the right palette — set it synchronously during render instead.
  document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
  document.documentElement.setAttribute("data-ui-theme", uiTheme);
  document.documentElement.setAttribute("data-ui-base-theme", uiThemeBase(uiTheme));

  useEffect(() => {
    // Chrome derives 12h/24h for datetime-local from <html lang>.
    // Keep it in sync with the app language so pickers always show 24h.
    document.documentElement.lang = i18n.language ?? "fr";
  }, [i18n.language]);

  return <FredUiContent />;
}

function FredUi() {
  return (
    <ApplicationContextProvider>
      <AppWithTheme />
    </ApplicationContextProvider>
  );
}

export default FredUi;
