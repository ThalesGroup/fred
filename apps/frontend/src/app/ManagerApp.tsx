// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useContext, useEffect, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import { GcuPageContent } from "@components/pages/GcuPage/GcuPage";
import BootstrapPage from "@components/pages/BootstrapPage/BootstrapPage";
import ProvisioningPage from "@components/pages/admin/ProvisioningPage/ProvisioningPage";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { getConfig } from "../common/config";
import { KeyCloakService } from "../security/KeycloakService";
import {
  useAcceptTermsMutation,
  useMeQuery,
  useMySpacesQuery,
  useOnboardingStatusQuery,
} from "../slices/fredManager/fredManagerApiEnhancements";
import { ApplicationContext, ApplicationThemeProvider } from "./ApplicationContextProvider";
import { uiThemeBase } from "./uiThemes";
import styles from "./ManagerApp.module.css";

function Retry({ retry }: { retry: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert">
      <p>{t("rework.manager.unavailable")}</p>
      <Button color="primary" variant="outlined" size="medium" onClick={retry}>
        {t("rework.provisioning.retryAuthority")}
      </Button>
    </div>
  );
}

function Memberships() {
  const { t } = useTranslation();
  const spaces = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  return (
    <>
      <PageHeader title={t("rework.manager.spaces")} />
      {spaces.isLoading ? (
        <p role="status">{t("common.loading")}</p>
      ) : spaces.isError ? (
        <Retry retry={() => void spaces.refetch()} />
      ) : !spaces.data?.length ? (
        <p>{t("rework.manager.empty")}</p>
      ) : (
        <ul className={styles.spaces}>
          {spaces.data.map((space) => (
            <li key={space.id}>
              <h2>{space.name}</h2>
              <p>{t(`rework.manager.kinds.${space.kind}`)}</p>
              <p>{space.path.map((id) => spaces.data?.find((parent) => parent.id === id)?.name ?? id).join(" / ")}</p>
              <p>{space.roles.map((role) => t(`rework.manager.roles.${role}`)).join(", ")}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function AdmittedJourney() {
  const { t } = useTranslation();
  const me = useMeQuery(undefined, { refetchOnMountOrArgChange: true });
  if (me.isLoading) return <p role="status">{t("common.loading")}</p>;
  if (me.isError || !me.data) return <Retry retry={() => void me.refetch()} />;
  return (
    <>
      <nav className={styles.navigation} aria-label={t("rework.manager.navigation")}>
        <Link to="/">{t("rework.manager.spaces")}</Link>
        {me.data.platform_roles.includes("platform_admin") && (
          <Link to="/admin/provisioning">{t("rework.provisioning.title")}</Link>
        )}
        <span>{me.data.username}</span>
      </nav>
      <Routes>
        <Route path="/" element={<Memberships />} />
        <Route path="/admin/provisioning" element={<ProvisioningPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

function Journey() {
  const { t, i18n } = useTranslation();
  const { darkMode, uiTheme } = useContext(ApplicationContext);
  const state = useOnboardingStatusQuery(undefined, { refetchOnMountOrArgChange: true });
  useRefetchOnWindowFocus(state.refetch, false);
  const [accept, acceptance] = useAcceptTermsMutation();
  const [acceptFailed, setAcceptFailed] = useState(false);
  document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
  document.documentElement.setAttribute("data-ui-theme", uiTheme);
  document.documentElement.setAttribute("data-ui-base-theme", uiThemeBase(uiTheme));
  useEffect(() => {
    document.documentElement.lang = i18n.language;
  }, [i18n.language]);

  let content;
  if (state.isLoading) content = <p role="status">{t("common.loading")}</p>;
  else if (state.isError || !state.data) content = <Retry retry={() => void state.refetch()} />;
  else if (state.data.gcu_version && state.data.acceptance?.version !== state.data.gcu_version) {
    const version = state.data.gcu_version;
    content = (
      <>
        {acceptFailed && <Retry retry={() => window.location.reload()} />}
        <GcuPageContent
          key={version}
          version={version}
          isLoading={acceptance.isLoading || state.isFetching}
          onAccept={async () => {
            setAcceptFailed(false);
            try {
              await accept({ termsRequest: { version } }).unwrap();
              await state.refetch().unwrap();
            } catch {
              setAcceptFailed(true);
            }
          }}
        />
      </>
    );
  } else if (state.data.root_bootstrap_required) content = <BootstrapPage />;
  else content = <AdmittedJourney />;
  return (
    <main className={styles.page}>
      <div className={styles.account}>
        <Button color="primary" variant="outlined" size="medium" onClick={() => KeyCloakService.CallLogout()}>
          {t("rework.manager.logout")}
        </Button>
      </div>
      <div className={styles.content}>{content}</div>
    </main>
  );
}

/** Experimental manager entry: only admitted memberships and provisioning are mounted. */
export default function ManagerApp() {
  return (
    <ApplicationThemeProvider platformUiThemes={null}>
      <BrowserRouter basename={getConfig().frontend_basename}>
        <Journey />
      </BrowserRouter>
    </ApplicationThemeProvider>
  );
}
