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
import React, { useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RouterProvider } from "react-router-dom";
import { ConfirmationDialogProvider } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { ToastProvider } from "@shared/molecules/Toast/ToastProvider";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { AuthProvider } from "../security/AuthContext";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";
import GcuGuard from "@core/guards/GcuGuard.tsx";
import BootstrapGuard from "@core/guards/BootstrapGuard.tsx";
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
        <img
          className={styles.logo}
          src={`${baseUrl}images/${darkMode ? logoNameDark : logoName}.svg`}
          alt={alt}
        />
        <span className={styles.srOnly}>{label}</span>
      </div>
    </div>
  );
};

function FredUiContent() {
  const [router, setRouter] = useState<any>(null);
  const { siteDisplayName, faviconName, logoName, faviconNameDark, logoNameDark } = useFrontendProperties();
  const { t } = useTranslation();
  const { darkMode } = useContext(ApplicationContext);
  const favicon = faviconName || logoName || "fred";
  const faviconDark = faviconNameDark || logoNameDark || "fred-dark";
  const baseUrl = (import.meta.env.BASE_URL ?? "/").endsWith("/")
    ? (import.meta.env.BASE_URL ?? "/")
    : `${import.meta.env.BASE_URL ?? "/"}/`;

  useEffect(() => {
    // Browser tab name = the app display name (config-driven via siteDisplayName,
    // same string as "<app> is coming soon" / the loading-screen alt).
    document.title = siteDisplayName;
    const faviconElement = document.getElementById("favicon") as HTMLLinkElement;
    faviconElement.href = `${baseUrl}images/${darkMode ? faviconDark : favicon}.svg`;
  }, [baseUrl, siteDisplayName, favicon, faviconDark, darkMode]);

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
        <GcuGuard>
          <BootstrapGuard>
            <ConfirmationDialogProvider>
              <ToastProvider>
                <RouterProvider router={router} />
              </ToastProvider>
            </ConfirmationDialogProvider>
          </BootstrapGuard>
        </GcuGuard>
      </AuthProvider>
    </React.Suspense>
  );
}

function AppWithTheme() {
  const { darkMode } = useContext(ApplicationContext);
  const { i18n } = useTranslation();

  // Effects run after render, which is too late for the first paint to pick
  // up the right palette — set it synchronously during render instead.
  document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");

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
